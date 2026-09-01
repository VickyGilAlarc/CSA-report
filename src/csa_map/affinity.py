"""Afinidad entre servicios y benchmark por industria.

Dos senales alimentan el score de oportunidad:

1. **Market basket** (``reglas_asociacion``): que servicios se compran juntos.
   Para cada par (A -> B) se calcula soporte, confianza y lift sobre las
   canastas de cada cuenta. Se construyen dos canastas por cuenta: la de
   servicios *ejecutados* (senal fuerte) y la de servicios *ofrecidos*
   (senal de como se arma comercialmente la conversacion).

2. **Benchmark de pares** (``adopcion_por_industria``): que porcentaje de las
   cuentas de la misma industria ya ejecuta el servicio. Responde a
   "tus comparables ya lo compran y esta cuenta no".
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

CANASTAS = {
    "ejecutado": ["EJECUTADO"],
    "ofrecido": ["EJECUTADO", "EN_CURSO", "EN_PAUSA", "PERDIDO"],
}


def _canastas(celdas_df: pd.DataFrame, estados: list[str]) -> dict[str, set[str]]:
    sel = celdas_df[celdas_df["cobertura"].isin(estados)]
    return {
        company: set(grupo["service_name"])
        for company, grupo in sel.groupby("company", observed=True)
    }


def reglas_asociacion(celdas_df: pd.DataFrame, tipo: str = "ejecutado",
                      soporte_minimo: int = 2, suavizado: float = 1.0) -> pd.DataFrame:
    """Reglas 'quien tiene A tambien tiene B' con soporte, confianza y lift."""
    canastas = _canastas(celdas_df, CANASTAS[tipo])
    n = len(canastas) or 1
    servicios = sorted({s for c in canastas.values() for s in c})

    conteo = {s: sum(1 for c in canastas.values() if s in c) for s in servicios}
    filas = []
    for a, b in itertools.permutations(servicios, 2):
        juntos = sum(1 for c in canastas.values() if a in c and b in c)
        if juntos < soporte_minimo:
            continue
        # Confianza suavizada: evita que 1 de 1 caso valga tanto como 5 de 5.
        confianza = (juntos + suavizado * conteo[b] / n) / (conteo[a] + suavizado)
        soporte_b = conteo[b] / n
        lift = confianza / soporte_b if soporte_b > 0 else np.nan
        filas.append(
            {
                "antecedente": a,
                "consecuente": b,
                "canasta": tipo,
                "cuentas_con_ambos": juntos,
                "cuentas_con_antecedente": conteo[a],
                "cuentas_con_consecuente": conteo[b],
                "soporte": round(juntos / n, 3),
                "confianza": round(float(confianza), 3),
                "lift": round(float(lift), 2) if pd.notna(lift) else None,
            }
        )
    cols = ["antecedente", "consecuente", "canasta", "cuentas_con_ambos",
            "cuentas_con_antecedente", "cuentas_con_consecuente", "soporte", "confianza", "lift"]
    if not filas:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(filas).sort_values(["lift", "confianza"], ascending=False).reset_index(drop=True)


def adopcion_por_industria(celdas_df: pd.DataFrame) -> pd.DataFrame:
    """% de cuentas de cada industria que ya ejecuta cada servicio."""
    df = celdas_df.assign(ejecutado=lambda d: d["cobertura"].eq("EJECUTADO").astype(int))
    agg = (
        df.groupby(["industria", "service_name"], observed=True)
        .agg(cuentas_industria=("company", "nunique"), cuentas_ejecutan=("ejecutado", "sum"))
        .reset_index()
    )
    agg["adopcion_industria_pct"] = (agg["cuentas_ejecutan"] / agg["cuentas_industria"] * 100).round(1)
    return agg


def afinidad_celdas(celdas_df: pd.DataFrame, soporte_minimo: int = 2,
                    suavizado: float = 1.0) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Afinidad 0-1 de cada cuenta con cada servicio, con su justificacion.

    Devuelve la tabla de afinidad por celda y las tablas de reglas usadas
    (para poder auditar de donde sale cada numero).
    """
    reglas = {
        tipo: reglas_asociacion(celdas_df, tipo, soporte_minimo, suavizado)
        for tipo in CANASTAS
    }
    canasta_ejec = _canastas(celdas_df, CANASTAS["ejecutado"])
    canasta_ofr = _canastas(celdas_df, CANASTAS["ofrecido"])

    indices = {}
    for tipo, tabla in reglas.items():
        if tabla.empty:
            indices[tipo] = {}
        else:
            indices[tipo] = {
                (r.antecedente, r.consecuente): (r.confianza, r.lift or 0.0)
                for r in tabla.itertuples()
            }

    adopcion = adopcion_por_industria(celdas_df)
    mapa_adopcion = {
        (r.industria, r.service_name): (r.adopcion_industria_pct, r.cuentas_ejecutan, r.cuentas_industria)
        for r in adopcion.itertuples()
    }

    # Adopcion global como piso cuando la industria tiene una sola cuenta.
    total_cuentas = celdas_df["company"].nunique()
    adopcion_global = (
        celdas_df.assign(e=lambda d: d["cobertura"].eq("EJECUTADO").astype(int))
        .groupby("service_name", observed=True)["e"].sum() / total_cuentas * 100
    ).to_dict()

    filas = []
    for r in celdas_df.itertuples():
        propios_ejec = canasta_ejec.get(r.company, set()) - {r.service_name}
        propios_ofr = canasta_ofr.get(r.company, set()) - {r.service_name}

        def _senal(propios, idx):
            valores = [idx[(a, r.service_name)] for a in propios if (a, r.service_name) in idx]
            if not valores:
                return 0.0, 0.0, 0
            # Se pondera la confianza por el lift: pesa mas lo que es
            # distintivamente co-ocurrente y no solo lo que es popular.
            conf = max(c for c, _ in valores)
            lift = max(l for _, l in valores)
            return conf, lift, len(valores)

        conf_e, lift_e, n_e = _senal(propios_ejec, indices["ejecutado"])
        conf_o, lift_o, n_o = _senal(propios_ofr, indices["ofrecido"])

        pct_ind, ejec_ind, n_ind = mapa_adopcion.get(
            (r.industria, r.service_name), (0.0, 0, 0)
        )
        # Con menos de 2 cuentas comparables la industria no informa: se usa el mercado.
        peer = pct_ind / 100 if n_ind >= 2 else adopcion_global.get(r.service_name, 0.0) / 100

        basket = 0.6 * conf_e + 0.4 * conf_o
        afinidad = min(1.0, 0.55 * basket + 0.45 * peer)

        filas.append(
            {
                "company": r.company,
                "service_name": r.service_name,
                "afinidad": round(float(afinidad), 4),
                "basket_confianza_ejecutado": round(conf_e, 3),
                "basket_lift_ejecutado": round(lift_e, 2),
                "basket_reglas_ejecutado": n_e,
                "basket_confianza_ofrecido": round(conf_o, 3),
                "basket_reglas_ofrecido": n_o,
                "adopcion_industria_pct": pct_ind,
                "cuentas_industria_ejecutan": int(ejec_ind),
                "cuentas_industria": int(n_ind),
                "peer_signal": round(float(peer), 3),
            }
        )
    return pd.DataFrame(filas), reglas
