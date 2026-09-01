"""Matriz de cobertura cuenta x servicio y perfil de cada cuenta.

La unidad de analisis del mapa es la *celda*: el cruce entre una cuenta y un
servicio del catalogo. Cada celda queda etiquetada con un unico estado de
cobertura, resolviendo por jerarquia cuando hay varios pitches en el cruce:

    EJECUTADO > EN_CURSO > EN_PAUSA > PERDIDO > BLANCO

``BLANCO`` es el espacio blanco puro: ese servicio nunca se le ofrecio a esa
cuenta, ni ganado ni perdido ni en pipeline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config

ORDEN_COBERTURA = ["EJECUTADO", "EN_CURSO", "EN_PAUSA", "PERDIDO", "BLANCO"]

ETIQUETA_COBERTURA = {
    "EJECUTADO": "Ejecutado",
    "EN_CURSO": "En curso",
    "EN_PAUSA": "En pausa",
    "PERDIDO": "Ofrecido y perdido",
    "BLANCO": "Nunca ofrecido",
}

# Marca compacta para leer la matriz de un vistazo.
SIMBOLO_COBERTURA = {
    "EJECUTADO": "EJEC",
    "EN_CURSO": "PITCH",
    "EN_PAUSA": "PAUSA",
    "PERDIDO": "PERD",
    "BLANCO": "",   # a proposito vacio: el espacio blanco se ve blanco
}


def _estado_celda(grupo: pd.DataFrame) -> str:
    if (grupo["categoria"] == "GANADO").any():
        return "EJECUTADO"
    abiertos = grupo.loc[grupo["categoria"] == "ABIERTO", "fase_cruda"]
    if len(abiertos):
        return "EN_PAUSA" if set(abiertos) == {"8.On Hold"} else "EN_CURSO"
    return "PERDIDO"


def celdas(cfg: Config, base: pd.DataFrame) -> pd.DataFrame:
    """Una fila por cruce cuenta x servicio del catalogo (incluye los blancos)."""
    cuentas = cfg.cuentas[cfg.cuentas["company"].isin(base["company"])].copy()
    servicios = cfg.taxonomia[cfg.taxonomia["en_catalogo"].astype(str).str.upper() == "SI"].copy()

    grilla = cuentas.assign(_k=1).merge(servicios.assign(_k=1), on="_k").drop(columns="_k")

    resumen = []
    for (company, service_name), grupo in base.groupby(["company", "service_name"], sort=False):
        ganados = grupo[grupo["categoria"] == "GANADO"]
        perdidos = grupo[grupo["categoria"] == "PERDIDO"]
        abiertos = grupo[grupo["categoria"] == "ABIERTO"]
        resumen.append(
            {
                "company": company,
                "service_name": service_name,
                "cobertura": _estado_celda(grupo),
                "n_pitches": len(grupo),
                "n_ganados": len(ganados),
                "n_perdidos": len(perdidos),
                "n_abiertos": len(abiertos),
                "revenue_ganado_eur": float(ganados["precio_eur"].sum(skipna=True)),
                "pipeline_abierto_eur": float(abiertos["precio_eur"].sum(skipna=True)),
                "valor_perdido_eur": float(perdidos["precio_eur"].sum(skipna=True)),
                "primer_contacto": grupo["fecha_referencia"].min(),
                "ultimo_movimiento": grupo["fecha_referencia"].max(),
                "ultima_derrota": perdidos["fecha_referencia"].max() if len(perdidos) else pd.NaT,
                "estados": " | ".join(
                    grupo.sort_values("orden_estado")["estado"].drop_duplicates().tolist()
                ),
            }
        )

    hist = pd.DataFrame(resumen)
    df = grilla.merge(hist, on=["company", "service_name"], how="left")

    df["cobertura"] = df["cobertura"].fillna("BLANCO")
    for col in ("n_pitches", "n_ganados", "n_perdidos", "n_abiertos",
                "revenue_ganado_eur", "pipeline_abierto_eur", "valor_perdido_eur"):
        df[col] = df[col].fillna(0)
    df["estados"] = df["estados"].fillna("")
    df["etiqueta_cobertura"] = df["cobertura"].map(ETIQUETA_COBERTURA)
    df["simbolo"] = df["cobertura"].map(SIMBOLO_COBERTURA)
    df["es_espacio_blanco"] = df["cobertura"] == "BLANCO"
    df["cobertura"] = pd.Categorical(df["cobertura"], categories=ORDEN_COBERTURA, ordered=True)
    return df.sort_values(["company", "familia", "servicio_normalizado"]).reset_index(drop=True)


def matriz(celdas_df: pd.DataFrame, valor: str = "simbolo") -> pd.DataFrame:
    """Pivot cuenta (filas) x servicio (columnas) para leer el mapa completo."""
    orden_servicios = (
        celdas_df[["familia", "servicio_normalizado"]]
        .drop_duplicates()
        .sort_values(["familia", "servicio_normalizado"])["servicio_normalizado"]
        .tolist()
    )
    piv = celdas_df.pivot_table(
        index="cuenta_normalizada",
        columns="servicio_normalizado",
        values=valor,
        aggfunc="first",
    )
    return piv.reindex(columns=orden_servicios)


def matriz_familia(celdas_df: pd.DataFrame) -> pd.DataFrame:
    """Cobertura agregada por familia: cuantos servicios de cada familia tiene la cuenta."""
    agg = (
        celdas_df.assign(ejecutado=lambda d: d["cobertura"].eq("EJECUTADO").astype(int))
        .groupby(["cuenta_normalizada", "familia"], observed=True)
        .agg(servicios_familia=("service_name", "count"), ejecutados=("ejecutado", "sum"))
        .reset_index()
    )
    agg["cobertura_pct"] = (agg["ejecutados"] / agg["servicios_familia"] * 100).round(1)
    return agg.pivot(index="cuenta_normalizada", columns="familia", values="cobertura_pct")


def perfil_cuentas(cfg: Config, base: pd.DataFrame, celdas_df: pd.DataFrame,
                   corte: pd.Timestamp) -> pd.DataFrame:
    """KPIs comerciales por cuenta: penetracion, win rate, revenue y recencia."""
    total_servicios = celdas_df["service_name"].nunique()

    g = base.groupby("company")
    perfil = pd.DataFrame(
        {
            "pitches_totales": g.size(),
            "pitches_ganados": g.apply(lambda d: (d["categoria"] == "GANADO").sum(), include_groups=False),
            "pitches_perdidos": g.apply(lambda d: (d["categoria"] == "PERDIDO").sum(), include_groups=False),
            "pitches_abiertos": g.apply(lambda d: (d["categoria"] == "ABIERTO").sum(), include_groups=False),
            "revenue_ganado_eur": g.apply(lambda d: d.loc[d["categoria"] == "GANADO", "precio_eur"].sum(), include_groups=False),
            "pipeline_abierto_eur": g.apply(lambda d: d.loc[d["categoria"] == "ABIERTO", "precio_eur"].sum(), include_groups=False),
            "valor_perdido_eur": g.apply(lambda d: d.loc[d["categoria"] == "PERDIDO", "precio_eur"].sum(), include_groups=False),
            "ultimo_movimiento": g["fecha_referencia"].max(),
            "primer_movimiento": g["fecha_referencia"].min(),
            "familias_tocadas": g["familia"].nunique(),
            "pilares_tocados": g["pilar"].nunique(),
        }
    ).reset_index()

    cob = (
        celdas_df.pivot_table(index="company", columns="cobertura", values="service_name",
                              aggfunc="count", observed=False)
        .reindex(columns=ORDEN_COBERTURA, fill_value=0)
        .fillna(0)
        .astype(int)
        .rename(columns={k: f"servicios_{k.lower()}" for k in ORDEN_COBERTURA})
        .reset_index()
    )
    perfil = perfil.merge(cob, on="company", how="left")

    fam_ganadas = (
        celdas_df[celdas_df["cobertura"] == "EJECUTADO"]
        .groupby("company", observed=True)["familia"].nunique()
        .rename("familias_ejecutadas")
        .reset_index()
    )
    perfil = perfil.merge(fam_ganadas, on="company", how="left")
    perfil["familias_ejecutadas"] = perfil["familias_ejecutadas"].fillna(0).astype(int)

    perfil["win_rate"] = np.where(
        (perfil["pitches_ganados"] + perfil["pitches_perdidos"]) > 0,
        perfil["pitches_ganados"] / (perfil["pitches_ganados"] + perfil["pitches_perdidos"]),
        np.nan,
    ).round(3)
    perfil["penetracion_catalogo_pct"] = (
        perfil["servicios_ejecutado"] / total_servicios * 100
    ).round(1)
    perfil["dias_sin_movimiento"] = (corte - perfil["ultimo_movimiento"]).dt.days

    # Madurez 0-100: mezcla amplitud de portafolio, revenue y efectividad.
    amplitud = perfil["servicios_ejecutado"] / max(total_servicios, 1)
    revenue = np.log1p(perfil["revenue_ganado_eur"].clip(lower=0))
    revenue = revenue / revenue.max() if revenue.max() > 0 else revenue
    efectividad = perfil["win_rate"].fillna(0)
    perfil["indice_madurez"] = (100 * (0.45 * amplitud + 0.35 * revenue + 0.20 * efectividad)).round(1)

    perfil = perfil.merge(cfg.cuentas.drop(columns=["notas"], errors="ignore"), on="company", how="left")

    columnas = [
        "company", "cuenta_normalizada", "industria", "grupo_economico", "tier_cuenta",
        "indice_madurez", "penetracion_catalogo_pct", "win_rate",
        "pitches_totales", "pitches_ganados", "pitches_perdidos", "pitches_abiertos",
        "revenue_ganado_eur", "pipeline_abierto_eur", "valor_perdido_eur",
        "servicios_ejecutado", "servicios_en_curso", "servicios_en_pausa",
        "servicios_perdido", "servicios_blanco",
        "familias_ejecutadas", "familias_tocadas", "pilares_tocados",
        "primer_movimiento", "ultimo_movimiento", "dias_sin_movimiento",
    ]
    return perfil[columnas].sort_values("indice_madurez", ascending=False).reset_index(drop=True)


def perfil_servicios(base: pd.DataFrame, celdas_df: pd.DataFrame,
                     corte: pd.Timestamp, meses_momentum: int) -> pd.DataFrame:
    """KPIs por servicio: demanda, win rate, ticket y momentum de mercado."""
    n_cuentas = celdas_df["company"].nunique()
    limite = corte - pd.DateOffset(months=meses_momentum)

    g = base.groupby("service_name")
    perf = pd.DataFrame(
        {
            "pitches": g.size(),
            "ganados": g.apply(lambda d: (d["categoria"] == "GANADO").sum(), include_groups=False),
            "perdidos": g.apply(lambda d: (d["categoria"] == "PERDIDO").sum(), include_groups=False),
            "abiertos": g.apply(lambda d: (d["categoria"] == "ABIERTO").sum(), include_groups=False),
            "revenue_eur": g.apply(lambda d: d.loc[d["categoria"] == "GANADO", "precio_eur"].sum(), include_groups=False),
            "ticket_mediano_eur": g["precio_eur"].median(),
            "ticket_promedio_eur": g["precio_eur"].mean(),
            "pitches_recientes": g.apply(lambda d: (d["fecha_referencia"] >= limite).sum(), include_groups=False),
            "ultimo_movimiento": g["fecha_referencia"].max(),
        }
    ).reset_index()

    cuentas_ganadoras = (
        base[base["categoria"] == "GANADO"].groupby("service_name")["company"].nunique()
        .rename("cuentas_con_servicio").reset_index()
    )
    cuentas_ofrecido = (
        base.groupby("service_name")["company"].nunique().rename("cuentas_ofrecido").reset_index()
    )
    perf = perf.merge(cuentas_ganadoras, on="service_name", how="left").merge(
        cuentas_ofrecido, on="service_name", how="left"
    )
    perf["cuentas_con_servicio"] = perf["cuentas_con_servicio"].fillna(0).astype(int)

    perf["win_rate"] = np.where(
        (perf["ganados"] + perf["perdidos"]) > 0,
        perf["ganados"] / (perf["ganados"] + perf["perdidos"]),
        np.nan,
    ).round(3)
    perf["penetracion_pct"] = (perf["cuentas_con_servicio"] / n_cuentas * 100).round(1)
    perf["cuentas_blanco"] = n_cuentas - perf["cuentas_ofrecido"]
    perf["momentum_pct"] = (perf["pitches_recientes"] / perf["pitches"] * 100).round(1)
    perf["dias_sin_movimiento"] = (corte - perf["ultimo_movimiento"]).dt.days

    tax = celdas_df[
        ["service_name", "servicio_normalizado", "label_corto", "familia", "subfamilia", "pilar",
         "modelo_comercial", "ticket_tipo"]
    ].drop_duplicates()
    perf = perf.merge(tax, on="service_name", how="left")

    columnas = [
        "servicio_normalizado", "label_corto", "service_name", "familia", "subfamilia", "pilar",
        "modelo_comercial", "ticket_tipo", "penetracion_pct", "win_rate", "momentum_pct",
        "ticket_mediano_eur", "ticket_promedio_eur", "revenue_eur",
        "pitches", "ganados", "perdidos", "abiertos",
        "cuentas_con_servicio", "cuentas_ofrecido", "cuentas_blanco",
        "ultimo_movimiento", "dias_sin_movimiento",
    ]
    return perf[columnas].sort_values(["penetracion_pct", "revenue_eur"], ascending=False).reset_index(drop=True)
