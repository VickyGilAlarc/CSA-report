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

from .config import Config

TIPO_OPORTUNIDAD = {
    "BLANCO": "Espacio blanco",
    "PERDIDO": "Reactivacion",
    "EN_PAUSA": "Rescate (en pausa)",
    "EN_CURSO": "En pipeline",
}


def _minmax(serie: pd.Series) -> pd.Series:
    s = serie.astype(float)
    rango = s.max() - s.min()
    if not np.isfinite(rango) or rango == 0:
        return pd.Series(0.5, index=s.index)
    return (s - s.min()) / rango


def _adyacencia(celdas_df: pd.DataFrame, objetivo: pd.DataFrame) -> pd.Series:
    """Que tan cerca esta el servicio del portafolio que la cuenta ya ejecuta.

    ``celdas_df`` debe ser la matriz completa (con las celdas ejecutadas), que es
    donde vive el anclaje; ``objetivo`` son las filas a puntuar.
    """
    ejec = celdas_df[celdas_df["cobertura"] == "EJECUTADO"]
    por_cuenta = {
        c: {
            "subfamilias": set(g["subfamilia"]),
            "familias": set(g["familia"]),
            "pilares": set(g["pilar"]),
        }
        for c, g in ejec.groupby("company", observed=True)
    }
    valores = []
    for r in objetivo.itertuples():
        perfil = por_cuenta.get(r.company)
        if not perfil:
            valores.append(0.10)          # cuenta sin nada ejecutado: sin anclaje
        elif r.subfamilia in perfil["subfamilias"]:
            valores.append(1.00)          # ya compra en la misma subfamilia
        elif r.familia in perfil["familias"]:
            valores.append(0.75)          # ya compra en la misma familia
        elif r.pilar in perfil["pilares"]:
            valores.append(0.50)          # ya compra en el mismo pilar
        else:
            valores.append(0.25)          # cliente activo, pero cruzando de pilar
    return pd.Series(valores, index=objetivo.index)


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
    if fila["adyacencia"] >= 0.75:
        partes.append(f"adyacente a {fila['familia']}, familia donde la cuenta ya compra")
    elif fila["adyacencia"] <= 0.25:
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
    return "; ".join(partes).capitalize() + "."


def _accion(fila) -> str:
    if fila["cobertura"] == "EN_PAUSA":
        return "Destrabar la propuesta en pausa con el contacto original"
    if fila["cobertura"] == "PERDIDO":
        return "Re-pitchear con nuevo angulo (revisar motivo de perdida)"
    if fila["adyacencia"] >= 0.75:
        return "Upsell directo sobre el servicio ya activo"
    if fila["adyacencia"] >= 0.50:
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
        ["service_name", "penetracion_pct", "win_rate", "momentum_pct",
         "ticket_mediano_eur", "dias_sin_movimiento"]
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
    ticket_mediano_global = perfil_serv["ticket_mediano_eur"].median(skipna=True)
    df["ticket_mediano_eur"] = df["ticket_mediano_eur"].fillna(ticket_mediano_global)

    df["c_demanda"] = 0.6 * _minmax(df["penetracion_pct"]) + 0.4 * df["win_rate"]
    df["c_afinidad"] = df["afinidad"].fillna(0)
    df["c_valor"] = _minmax(np.log1p(df["ticket_mediano_eur"].clip(lower=0)))

    dias_serv = df["dias_sin_movimiento_servicio"].fillna(999)
    decaimiento = np.exp(-dias_serv / 365.0)          # semivida ~ 8 meses
    df["c_momentum"] = 0.5 * (df["momentum_pct"] / 100) + 0.5 * decaimiento
    df["c_adyacencia"] = _adyacencia(celdas_df, df)
    df["adyacencia"] = df["c_adyacencia"]

    df["score_base"] = 100 * (
        pesos["demanda"] * df["c_demanda"]
        + pesos["afinidad"] * df["c_afinidad"]
        + pesos["valor"] * df["c_valor"]
        + pesos["momentum"] * df["c_momentum"]
        + pesos["adyacencia"] * df["c_adyacencia"]
    )

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

    umbrales = sc["umbrales_prioridad"]
    df["prioridad"] = np.select(
        [df["score"] >= umbrales["A"], df["score"] >= umbrales["B"]],
        ["A", "B"],
        default="C",
    )
    df["tipo_oportunidad"] = df["cobertura"].astype(str).map(TIPO_OPORTUNIDAD)
    df["reactivable"] = np.where(
        df["cobertura"] == "PERDIDO",
        df["dias_desde_derrota"] >= react["dias_para_repitch"],
        pd.NA,
    )
    df["valor_potencial_eur"] = df["ticket_mediano_eur"].round(0)
    df["motivo"] = df.apply(_motivo, axis=1)
    df["accion_sugerida"] = df.apply(_accion, axis=1)

    df["ranking_en_cuenta"] = (
        df.groupby("company")["score"].rank(ascending=False, method="first").astype(int)
    )

    columnas = [
        "cuenta_normalizada", "company", "industria", "tier_cuenta",
        "servicio_normalizado", "service_name", "familia", "subfamilia", "pilar",
        "modelo_comercial", "ticket_tipo",
        "cobertura", "etiqueta_cobertura", "tipo_oportunidad",
        "score", "prioridad", "ranking_en_cuenta", "valor_potencial_eur",
        "c_demanda", "c_afinidad", "c_valor", "c_momentum", "c_adyacencia",
        "score_base", "factor_estado", "factor_recencia",
        "penetracion_pct", "win_rate", "momentum_pct",
        "adopcion_industria_pct", "cuentas_industria_ejecutan", "cuentas_industria",
        "basket_confianza_ejecutado", "basket_lift_ejecutado",
        "n_pitches", "n_perdidos", "ultima_derrota", "dias_desde_derrota", "reactivable",
        "ultimo_movimiento", "motivo", "accion_sugerida",
    ]
    salida = df[columnas].copy()
    for col in ("c_demanda", "c_afinidad", "c_valor", "c_momentum", "c_adyacencia", "score_base"):
        salida[col] = salida[col].round(3)
    return salida.sort_values(["score", "cuenta_normalizada"], ascending=[False, True]).reset_index(drop=True)


def top_por_cuenta(oportunidades: pd.DataFrame, n: int) -> pd.DataFrame:
    """Vista ejecutiva: las N mejores jugadas de cada cuenta."""
    return (
        oportunidades[oportunidades["ranking_en_cuenta"] <= n]
        .sort_values(["cuenta_normalizada", "ranking_en_cuenta"])
        .reset_index(drop=True)
    )
