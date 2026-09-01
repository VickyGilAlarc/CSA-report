"""Orquestador: de export crudo a mapa completo.

``construir()`` devuelve un diccionario con todas las tablas del mapa, que es
lo que consumen tanto el reporte Excel como el dashboard HTML.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from . import affinity, coverage, ingest, scoring
from .config import Config, cargar


@dataclass
class Mapa:
    cfg: Config
    corte: pd.Timestamp
    base: pd.DataFrame
    celdas: pd.DataFrame
    matriz_estado: pd.DataFrame
    matriz_familia: pd.DataFrame
    perfil_cuentas: pd.DataFrame
    perfil_servicios: pd.DataFrame
    afinidad: pd.DataFrame
    reglas: dict[str, pd.DataFrame]
    adopcion_industria: pd.DataFrame
    oportunidades: pd.DataFrame
    top_oportunidades: pd.DataFrame
    pipeline_abierto: pd.DataFrame
    resumen: dict[str, Any] = field(default_factory=dict)


def construir(cfg: Config | None = None) -> Mapa:
    cfg = cfg or cargar()
    base = ingest.normalizar(cfg)
    corte = ingest.fecha_corte(cfg, base)

    meses = cfg.params["ventanas"]["meses_momentum"]
    celdas = coverage.celdas(cfg, base)
    perfil_cta = coverage.perfil_cuentas(cfg, base, celdas, corte)
    perfil_srv = coverage.perfil_servicios(base, celdas, corte, meses)

    par_af = cfg.params["afinidad"]
    afin, reglas = affinity.afinidad_celdas(
        celdas, par_af["soporte_minimo"], par_af["suavizado"]
    )
    adopcion = affinity.adopcion_por_industria(celdas)

    oportunidades = scoring.puntuar(cfg, celdas, afin, perfil_srv, corte)
    top = scoring.top_por_cuenta(oportunidades, cfg.scoring["top_por_cuenta"])

    pipeline_abierto = (
        base[base["es_abierto"]]
        .sort_values(["orden_estado", "precio_eur"], ascending=[True, False])
        [["cuenta_normalizada", "industria", "servicio_normalizado", "familia", "pilar",
          "nombre_pitch", "estado", "fecha_brief", "fecha_referencia", "precio_eur", "contacto"]]
        .reset_index(drop=True)
    )

    resumen = {
        "fecha_corte": corte,
        "n_pitches": len(base),
        "n_cuentas": base["company"].nunique(),
        "n_servicios_catalogo": celdas["service_name"].nunique(),
        "n_celdas": len(celdas),
        "n_ejecutado": int((celdas["cobertura"] == "EJECUTADO").sum()),
        "n_en_curso": int((celdas["cobertura"] == "EN_CURSO").sum()),
        "n_en_pausa": int((celdas["cobertura"] == "EN_PAUSA").sum()),
        "n_perdido": int((celdas["cobertura"] == "PERDIDO").sum()),
        "n_blanco": int((celdas["cobertura"] == "BLANCO").sum()),
        "cobertura_pct": round((celdas["cobertura"] == "EJECUTADO").mean() * 100, 1),
        "revenue_ganado_eur": float(base.loc[base["categoria"] == "GANADO", "precio_eur"].sum()),
        "pipeline_abierto_eur": float(base.loc[base["categoria"] == "ABIERTO", "precio_eur"].sum()),
        "valor_perdido_eur": float(base.loc[base["categoria"] == "PERDIDO", "precio_eur"].sum()),
        "win_rate_global": round(
            (base["categoria"] == "GANADO").sum()
            / max((base["categoria"].isin(["GANADO", "PERDIDO"])).sum(), 1),
            3,
        ),
        "oportunidades_A": int((oportunidades["prioridad"] == "A").sum()),
        "oportunidades_B": int((oportunidades["prioridad"] == "B").sum()),
        "valor_espacios_blancos_eur": float(
            oportunidades.loc[oportunidades["prioridad"].isin(["A", "B"]), "valor_potencial_eur"].sum()
        ),
    }

    return Mapa(
        cfg=cfg,
        corte=corte,
        base=base,
        celdas=celdas,
        matriz_estado=coverage.matriz(celdas, "simbolo"),
        matriz_familia=coverage.matriz_familia(celdas),
        perfil_cuentas=perfil_cta,
        perfil_servicios=perfil_srv,
        afinidad=afin,
        reglas=reglas,
        adopcion_industria=adopcion,
        oportunidades=oportunidades,
        top_oportunidades=top,
        pipeline_abierto=pipeline_abierto,
        resumen=resumen,
    )
