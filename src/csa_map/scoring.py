"""Scoring de oportunidades: prioriza los espacios blancos de cada cuenta.

Cada celda que no esta ejecutada recibe un score 0-100 compuesto por cinco
senales, cada una normalizada a 0-1 y ponderada segun ``config/parametros.yaml``:

    demanda     que tan vendible es el servicio en el portafolio Chile
    afinidad    market basket + adopcion de cuentas comparables
    valor       ticket potencial del servicio
    momentum    actividad reciente del servicio en el mercado
    adyacencia  cercania al portafolio que la cuenta ya tiene hoy

El score se multiplica por un factor segun el estado actual de la celda
(nunca ofrecido pesa mas que un perdido reciente) y se traduce a prioridad
A / B / C, con un motivo en texto que explica por que subio o bajo.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import substitution
from .config import Config

TIPO_OPORTUNIDAD = {
    "BLANCO": "Espacio blanco",
    "PERDIDO": "Reactivacion",
    "EN_PAUSA": "Rescate (en pausa)",
    "EN_CURSO": "En pipeline",
}


def _escalar(serie: pd.Series, lo: float, hi: float) -> pd.Series:
    """Normaliza a 0-1 contra una escala fija, para poder recalcular sin sesgo."""
    if not np.isfinite(hi - lo) or hi == lo:
        return pd.Series(0.5, index=serie.index)
    return ((serie - lo) / (hi - lo)).clip(0, 1)


def _minmax(serie: pd.Series) -> pd.Series:
    s = serie.astype(float)
    rango = s.max() - s.min()
    if not np.isfinite(rango) or rango == 0:
        return pd.Series(0.5, index=s.index)
    return (s - s.min()) / rango


# Escalera de adyacencia, de lo mas fino a lo mas grueso del catalogo ZOHO.
# Los pesos bajan rapido porque "Tech Consulting" agrupa mas de la mitad del
# catalogo: compartir scope dice bastante menos que compartir business category.
ESCALERA_ADYACENCIA = [
    ("subfamilia", 1.00, "misma categoria de negocio"),
    ("familia",    0.60, "mismo scope de servicio"),
    ("capability", 0.45, "misma capability"),
    ("pilar",      0.35, "mismo pilar"),
]
ADYACENCIA_SIN_ANCLAJE = 0.20   # cuenta activa, pero cruzando de pilar
ADYACENCIA_SIN_CUENTA = 0.10    # cuenta sin nada ejecutado


def _adyacencia(celdas_df: pd.DataFrame, objetivo: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Que tan cerca esta el servicio del portafolio que la cuenta ya ejecuta.

    ``celdas_df`` debe ser la matriz completa (con las celdas ejecutadas), que es
    donde vive el anclaje; ``objetivo`` son las filas a puntuar. Devuelve el valor
    0-1 y la etiqueta del nivel de la escalera con el que se engancho, para poder
    explicar el score en palabras.
    """
    ejec = celdas_df[celdas_df["cobertura"] == "EJECUTADO"]
    niveles = [n for n, _, _ in ESCALERA_ADYACENCIA]
    por_cuenta = {
        c: {n: set(g[n]) for n in niveles}
        for c, g in ejec.groupby("company", observed=True)
    }
    valores, anclajes = [], []
    for r in objetivo.itertuples():
        perfil = por_cuenta.get(r.company)
        if not perfil:
            valores.append(ADYACENCIA_SIN_CUENTA)
            anclajes.append(None)
            continue
        for nivel, peso, etiqueta in ESCALERA_ADYACENCIA:
            if getattr(r, nivel) in perfil[nivel]:
                valores.append(peso)
                anclajes.append(f"{etiqueta} ({getattr(r, nivel)})")
                break
        else:
            valores.append(ADYACENCIA_SIN_ANCLAJE)
            anclajes.append(None)
    idx = objetivo.index
    return pd.Series(valores, index=idx), pd.Series(anclajes, index=idx)


def _motivo(fila) -> str:
    partes = []
    if fila["cuentas_industria"] >= 2 and fila["cuentas_industria_ejecutan"] > 0:
        partes.append(
            f"{fila['cuentas_industria_ejecutan']} de {fila['cuentas_industria']} cuentas "
            f"de {fila['industria']} ya lo ejecutan"
        )
    if fila["basket_reglas_ejecutado"] > 0 and fila["basket_lift_ejecutado"] >= 1.2:
        partes.append(
            f"co-ocurre con servicios que la cuenta ya tiene (lift {fila['basket_lift_ejecutado']:.1f})"
        )
    if fila["adyacencia"] >= 1.00:
        partes.append(f"la cuenta ya compra en {fila['subfamilia']}, la misma categoria")
    elif pd.notna(fila["anclaje"]):
        partes.append(f"engancha por {fila['anclaje']}")
    else:
        partes.append("sin anclaje en el portafolio actual de la cuenta")
    if fila["momentum_pct"] >= 60:
        partes.append("servicio con demanda activa en los ultimos meses")
    elif fila["dias_sin_movimiento_servicio"] and fila["dias_sin_movimiento_servicio"] > 365:
        partes.append("servicio sin movimiento en el mercado hace mas de un ano")
    if fila["cobertura"] == "PERDIDO":
        dias = fila.get("dias_desde_derrota")
        if pd.notna(dias):
            partes.append(f"se perdio hace {int(dias)} dias")
    if fila["cobertura"] == "EN_PAUSA":
        partes.append("quedo en pausa: falta destrabar")
    if not partes:
        partes.append("oportunidad de catalogo sin senales de traccion aun")
    texto = "; ".join(partes)
    # capitalize() minusculizaria los nombres propios del resto de la frase.
    return texto[:1].upper() + texto[1:] + "."


def _accion(fila) -> str:
    if fila["rol_en_grupo"] == "UPGRADE":
        return f"Proponer el salto de escalon desde {fila['cubierto_por']}"
    if fila["cobertura"] == "EN_PAUSA":
        return "Destrabar la propuesta en pausa con el contacto original"
    if fila["cobertura"] == "PERDIDO":
        return "Re-pitchear con nuevo angulo (revisar motivo de perdida)"
    if fila["rol_en_grupo"] == "REPRESENTANTE":
        return "Elegir la variante con el cliente antes de cotizar"
    if fila["adyacencia"] >= 1.00:
        return "Upsell directo sobre la categoria que ya compra"
    if fila["adyacencia"] >= 0.45:
        return "Cross-sell apoyado en el equipo que ya atiende la cuenta"
    if fila["adyacencia"] >= 0.35:
        return "Cross-sell dentro del mismo pilar"
    if fila["ticket_tipo"] == "Bajo":
        return "Usar como abrepuertas de bajo ticket"
    return "Construir caso con benchmark de la industria antes de pitchear"


def puntuar(cfg: Config, celdas_df: pd.DataFrame, afinidad_df: pd.DataFrame,
            perfil_serv: pd.DataFrame, corte: pd.Timestamp) -> pd.DataFrame:
    """Devuelve todas las celdas no ejecutadas, puntuadas y priorizadas."""
    sc = cfg.scoring
    pesos = sc["pesos"]

    serv = perfil_serv[
        ["service_name", "penetracion_pct", "win_rate", "momentum_pct", "dias_sin_movimiento"]
    ].rename(columns={"dias_sin_movimiento": "dias_sin_movimiento_servicio"})

    df = (
        celdas_df.merge(afinidad_df, on=["company", "service_name"], how="left")
        .merge(serv, on="service_name", how="left")
    )
    # Se puntua lo que NO esta cerrado ni ya en conversacion: el pipeline abierto
    # se sigue en su propia vista, no compite como oportunidad a abrir.
    df = df[~df["cobertura"].isin(["EJECUTADO", "EN_CURSO"])].copy()

    # --- componentes 0-1 ---------------------------------------------------
    win_rate_global = perfil_serv["win_rate"].mean(skipna=True)
    df["win_rate"] = df["win_rate"].fillna(win_rate_global)
    df["penetracion_pct"] = df["penetracion_pct"].fillna(0)
    df["momentum_pct"] = df["momentum_pct"].fillna(0)
    df["c_demanda"] = 0.6 * _minmax(df["penetracion_pct"]) + 0.4 * df["win_rate"]
    df["c_afinidad"] = df["afinidad"].fillna(0)
    # El eje de valor se calibra sobre TODO el universo, no sobre la sub-tabla,
    # para que el upgrade (valorizado por su delta) se compare contra lo mismo.
    log_ref = np.log1p(df["valor_anual_eur"].clip(lower=0))
    lo, hi = float(log_ref.min()), float(log_ref.max())
    df.attrs["escala_valor"] = (lo, hi)
    df["c_valor"] = _escalar(log_ref, lo, hi)

    dias_serv = df["dias_sin_movimiento_servicio"].fillna(999)
    decaimiento = np.exp(-dias_serv / 365.0)          # semivida ~ 8 meses
    df["c_momentum"] = 0.5 * (df["momentum_pct"] / 100) + 0.5 * decaimiento
    df["c_adyacencia"], df["anclaje"] = _adyacencia(celdas_df, df)
    df["adyacencia"] = df["c_adyacencia"]

    def _componer(valor_norm: pd.Series) -> pd.Series:
        return 100 * (
            pesos["demanda"] * df["c_demanda"]
            + pesos["afinidad"] * df["c_afinidad"]
            + pesos["valor"] * valor_norm
            + pesos["momentum"] * df["c_momentum"]
            + pesos["adyacencia"] * df["c_adyacencia"]
        )

    # --- pasada 1: score con el precio completo del servicio --------------
    df["score_base_prelim"] = _componer(df["c_valor"])

    # --- roles de grupo: aqui se separa oportunidad real de duplicado -----
    df = substitution.asignar_roles(celdas_df, df, cfg.params.get("sustitucion", {}))

    # --- pasada 2: un upgrade vale su delta, no el precio de lista --------
    lo, hi = df.attrs.get("escala_valor", (0.0, 1.0))
    df["c_valor"] = _escalar(np.log1p(df["valor_oportunidad_eur"].clip(lower=0)), lo, hi)
    df["score_base"] = _componer(df["c_valor"])

    # --- factores por estado y recencia de la derrota ----------------------
    factores = sc["factor_estado"]
    df["factor_estado"] = df["cobertura"].astype(str).map(factores).fillna(0.0)

    react = sc["reactivacion"]
    df["dias_desde_derrota"] = (corte - pd.to_datetime(df["ultima_derrota"])).dt.days
    reciente = (df["cobertura"] == "PERDIDO") & (
        df["dias_desde_derrota"] < react["dias_para_repitch"]
    )
    df["factor_recencia"] = np.where(reciente, react["penalizacion_reciente"], 1.0)

    df["score"] = (df["score_base"] * df["factor_estado"] * df["factor_recencia"]).round(1)
    # Alternativas y cubiertas conservan su score para poder compararlas, pero
    # quedan fuera del ranking: no se cuentan dos veces ni compiten por prioridad.
    df["score_neto"] = np.where(df["oportunidad_neta"], df["score"], np.nan)

    umbrales = sc["umbrales_prioridad"]
    df["prioridad"] = np.select(
        [~df["oportunidad_neta"], df["score"] >= umbrales["A"], df["score"] >= umbrales["B"]],
        ["-", "A", "B"],
        default="C",
    )
    df["tipo_oportunidad"] = np.where(
        df["rol_en_grupo"] == "UPGRADE", "Upgrade",
        df["cobertura"].astype(str).map(TIPO_OPORTUNIDAD),
    )
    df["reactivable"] = np.where(
        df["cobertura"] == "PERDIDO",
        df["dias_desde_derrota"] >= react["dias_para_repitch"],
        pd.NA,
    )
    df["valor_potencial_eur"] = df["valor_oportunidad_eur"].round(0)
    df["modalidad_valor"] = np.where(
        df["valor_anual_eur"] > df["valor_referencia_eur"], "SRP mensual anualizado (x12)",
        np.where(df["fuente_valor"].eq("Historico CL"), "Valor cerrado en Chile", "Valor de lista"),
    )
    df["motivo"] = df.apply(_motivo, axis=1)
    df["accion_sugerida"] = df.apply(_accion, axis=1)

    # El ranking por cuenta solo ordena oportunidades netas.
    df["ranking_en_cuenta"] = (
        df["score_neto"].groupby(df["company"]).rank(ascending=False, method="first")
    )

    columnas = [
        "cuenta_normalizada", "company", "industria", "tier_cuenta",
        "servicio_normalizado", "service_name", "familia", "subfamilia", "pilar",
        "modalidad", "ticket_tipo", "activo",
        "grupo_sustitucion", "regla_grupo", "descripcion_regla", "nivel", "rol_en_grupo", "etiqueta_rol",
        "oportunidad_neta", "cubierto_por", "nivel_base", "motivo_grupo",
        "cobertura", "etiqueta_cobertura", "tipo_oportunidad",
        "score", "score_neto", "prioridad", "ranking_en_cuenta",
        "valor_potencial_eur", "valor_referencia_eur", "valor_anual_eur", "fuente_valor", "modalidad_valor",
        "c_demanda", "c_afinidad", "c_valor", "c_momentum", "c_adyacencia",
        "score_base", "factor_estado", "factor_recencia",
        "penetracion_pct", "win_rate", "momentum_pct",
        "adopcion_industria_pct", "cuentas_industria_ejecutan", "cuentas_industria",
        "basket_confianza_ejecutado", "basket_lift_ejecutado", "anclaje",
        "n_pitches", "n_perdidos", "ultima_derrota", "dias_desde_derrota", "reactivable",
        "ultimo_movimiento", "motivo", "accion_sugerida",
    ]
    salida = df[columnas].copy()
    for col in ("c_demanda", "c_afinidad", "c_valor", "c_momentum", "c_adyacencia", "score_base"):
        salida[col] = salida[col].round(3)
    return salida.sort_values(
        ["oportunidad_neta", "score", "cuenta_normalizada"], ascending=[False, False, True]
    ).reset_index(drop=True)


def top_por_cuenta(oportunidades: pd.DataFrame, n: int) -> pd.DataFrame:
    """Vista ejecutiva: las N mejores jugadas netas de cada cuenta."""
    return (
        oportunidades[oportunidades["ranking_en_cuenta"].le(n)]
        .sort_values(["cuenta_normalizada", "ranking_en_cuenta"])
        .reset_index(drop=True)
    )
