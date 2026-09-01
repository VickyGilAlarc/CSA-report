"""Ingesta y normalizacion del reporte de pitches del CRM.

Convierte el export crudo (con cabecera decorativa, precios como texto y fases
codificadas) en una tabla plana de una fila por pitch, ya enriquecida con la
taxonomia de servicios y la ficha de cuentas.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .config import Config

# Lo que el catalogo aporta a cada pitch. El catalogo es la fuente de verdad de
# la jerarquia de servicios; el CRM solo aporta el nombre.
COLUMNAS_CATALOGO = [
    "service_name", "servicio_normalizado", "label_corto", "pilar", "familia", "subfamilia",
    "capability", "origen", "modalidad", "ticket_tipo", "grupo_sustitucion", "regla_grupo",
    "descripcion_regla", "nivel", "srp_eur", "costo_eur", "min_revenue_eur", "meses_estimados",
    "activo", "es_singleton",
]

COLUMNAS_FUENTE = {
    "COMPANY": "company",
    "Nombre de Pitch": "nombre_pitch",
    "Brief Received On": "fecha_brief",
    "PROJECT DESCRIPTION & COMMENTS": "comentarios",
    "Date Pitch Won, Lost ,On Hold": "fecha_resolucion",
    "Contact - Last Name": "contacto",
    "Moneda": "moneda_local",
    "PROJECT PRICE (Lcy) (Registrar moneda)": "precio_moneda_local",
    "Tasa de cambio": "tasa_cambio",
    "PROJECT PRICE (Lcy)": "precio_eur",
    "CSA COST 2026": "costo_csa",
    "Bonified": "bonificado",
    "Fase": "fase_cruda",
    "Service name": "service_name",
    "New Core Pillar": "pilar_crm",
}


def _a_numero(valor) -> float | None:
    """Convierte '€ 5,818' / '3.834.000' / 3235.17 a float."""
    if pd.isna(valor):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = re.sub(r"[^\d,.\-]", "", str(valor)).strip()
    if texto in {"", "-", "."}:
        return None
    # Si hay coma y punto, la ultima ocurrencia manda como separador decimal.
    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        entero, _, decimal = texto.rpartition(",")
        texto = f"{entero.replace(',', '')}.{decimal}" if len(decimal) in (1, 2) else texto.replace(",", "")
    try:
        return float(texto)
    except ValueError:
        return None


def leer_crudo(cfg: Config) -> pd.DataFrame:
    fuente = cfg.fuente
    ruta: Path = cfg.ruta_fuente()
    if not ruta.exists():
        raise FileNotFoundError(f"No se encuentra el archivo fuente: {ruta}")
    df = pd.read_excel(ruta, sheet_name=fuente["hoja"], header=fuente["fila_encabezado"] - 1)
    faltantes = [c for c in COLUMNAS_FUENTE if c not in df.columns]
    if faltantes:
        raise ValueError(f"El export no trae las columnas esperadas: {faltantes}")
    return df


def normalizar(cfg: Config, df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Devuelve la base normalizada: una fila por pitch, lista para analizar."""
    if df is None:
        df = leer_crudo(cfg)

    base = df.rename(columns=COLUMNAS_FUENTE)[list(COLUMNAS_FUENTE.values())].copy()
    base = base.dropna(subset=["company", "service_name"], how="any")

    for col in ("company", "service_name", "fase_cruda", "pilar_crm", "nombre_pitch"):
        base[col] = base[col].astype(str).str.strip()

    for col in ("fecha_brief", "fecha_resolucion"):
        base[col] = pd.to_datetime(base[col], errors="coerce")

    for col in ("precio_moneda_local", "tasa_cambio", "precio_eur", "costo_csa"):
        base[col] = base[col].map(_a_numero)

    base["bonificado"] = (
        base["bonificado"].astype(str).str.strip().str.lower().map({"yes": True, "no": False})
    )

    # --- fases -> estado legible + categoria ------------------------------
    fases = cfg.fases
    desconocidas = sorted(set(base["fase_cruda"]) - set(fases))
    if desconocidas:
        raise ValueError(
            f"Fases no mapeadas en config/parametros.yaml: {desconocidas}. Agregalas al bloque 'fases'."
        )
    base["estado"] = base["fase_cruda"].map(lambda f: fases[f]["estado"])
    base["categoria"] = base["fase_cruda"].map(lambda f: fases[f]["categoria"])
    base["orden_estado"] = base["fase_cruda"].map(lambda f: fases[f]["orden"])
    base["es_abierto"] = base["fase_cruda"].map(lambda f: fases[f]["abierto"])

    # --- enriquecimiento con el catalogo oficial y la ficha de cuentas -----
    base["service_name"] = base["service_name"].str.replace(r"\s+", " ", regex=True)
    cat = cfg.catalogo[COLUMNAS_CATALOGO]
    sin_catalogo = sorted(set(base["service_name"]) - set(cat["service_name"]))
    if sin_catalogo:
        raise ValueError(
            "Servicios pitcheados que no existen en el catalogo ZOHO: "
            f"{sin_catalogo}. Revisa el nombre en el CRM o agregalos al catalogo."
        )
    base = base.merge(cat, on="service_name", how="left")

    cuentas = cfg.cuentas.drop(columns=[c for c in ("notas",) if c in cfg.cuentas.columns])
    sin_ficha = sorted(set(base["company"]) - set(cuentas["company"]))
    if sin_ficha:
        raise ValueError(
            f"Cuentas sin ficha en config/cuentas.csv: {sin_ficha}. Agregalas para clasificar la industria."
        )
    base = base.merge(cuentas, on="company", how="left")

    # El pilar de la taxonomia manda; se deja traza si el CRM discrepa.
    base["discrepancia_pilar"] = base["pilar_crm"] != base["pilar"]

    base["fecha_referencia"] = base["fecha_resolucion"].fillna(base["fecha_brief"])
    base["anio"] = base["fecha_referencia"].dt.year
    base["trimestre"] = base["fecha_referencia"].dt.to_period("Q").astype(str)

    base["id_pitch"] = [f"P{n:04d}" for n in range(1, len(base) + 1)]

    columnas = [
        "id_pitch", "company", "cuenta_normalizada", "industria", "grupo_economico", "tier_cuenta",
        "nombre_pitch", "service_name", "servicio_normalizado", "label_corto", "familia", "subfamilia",
        "capability", "origen", "pilar", "pilar_crm", "discrepancia_pilar", "modalidad", "ticket_tipo",
        "grupo_sustitucion", "regla_grupo", "nivel", "srp_eur", "activo",
        "fase_cruda", "estado", "categoria", "orden_estado", "es_abierto",
        "fecha_brief", "fecha_resolucion", "fecha_referencia", "anio", "trimestre",
        "moneda_local", "precio_moneda_local", "tasa_cambio", "precio_eur", "costo_csa",
        "bonificado", "contacto", "comentarios",
    ]
    return base[columnas].sort_values(["company", "fecha_referencia"]).reset_index(drop=True)


def fecha_corte(cfg: Config, base: pd.DataFrame) -> pd.Timestamp:
    configurada = cfg.params.get("ventanas", {}).get("fecha_corte")
    if configurada:
        return pd.Timestamp(configurada)
    return pd.Timestamp(base["fecha_referencia"].max())
