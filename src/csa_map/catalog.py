"""Catalogo de servicios: fuente de verdad para el universo del mapa.

Lee el export de ZOHO (`data/raw/ZOHO_Catalogo_CSA_Latam.xlsx`), que trae la
jerarquia oficial `Pillar -> Scope Of Service -> Business Category -> Service`
con precios de lista en EUR, y le adosa dos capas curadas que viven en `config/`:

* `servicios_reglas.csv`  — etiqueta corta, grupo de sustitucion, nivel y modalidad.
* `grupos_sustitucion.csv` — la regla de cada grupo y por que existe.

El grupo de sustitucion es lo que permite distinguir una oportunidad real de un
esfuerzo duplicado: tres variantes de ODO no son tres oportunidades.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

COLUMNAS_ZOHO = {
    "Id": "id_catalogo",
    "Pillar": "pilar",
    "Scope Of Service": "scope",
    "Capability": "capability",
    "Grupped": "origen",
    "Business Category": "subfamilia",
    "Service Name": "service_name",
    "Tiempo estimado en meses": "meses_estimados",
    "CSA COST \nEURO 2025": "costo_eur",
    "Minimum revenue in P&L\nEURO 2025": "min_revenue_eur",
    "SRP\nEURO 2025": "srp_eur",
    "Status": "estado_catalogo",
}

REGLAS_VALIDAS = {"EXCLUSIVO", "ESCALABLE", "ACUMULABLE"}


def _normalizar_texto(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .str.replace("​", "", regex=False)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )


def cargar_catalogo(ruta_zoho: Path, dir_config: Path, hoja: str = "Catalogo de servicios") -> pd.DataFrame:
    if not ruta_zoho.exists():
        raise FileNotFoundError(f"No se encuentra el catalogo ZOHO: {ruta_zoho}")

    raw = pd.read_excel(ruta_zoho, sheet_name=hoja)
    faltantes = [c for c in COLUMNAS_ZOHO if c not in raw.columns]
    if faltantes:
        raise ValueError(f"El catalogo ZOHO no trae las columnas esperadas: {faltantes}")

    cat = raw.rename(columns=COLUMNAS_ZOHO)[list(COLUMNAS_ZOHO.values())].copy()
    cat = cat[cat["service_name"].notna()].copy()
    for col in ("service_name", "pilar", "scope", "subfamilia", "capability", "origen", "estado_catalogo"):
        cat[col] = _normalizar_texto(cat[col]).replace({"nan": None})

    duplicados = cat["service_name"].duplicated()
    if duplicados.any():
        raise ValueError(f"Servicios repetidos en el catalogo ZOHO: {cat.loc[duplicados,'service_name'].tolist()}")

    # "CSA Tech - Tech Consulting" -> "Tech Consulting": el pilar ya va aparte.
    cat["familia"] = cat["scope"].str.replace(r"^CSA (Tech|Science)\s*-\s*", "", regex=True)
    cat["subfamilia"] = cat["subfamilia"].fillna("Sin categoria")

    for col in ("costo_eur", "min_revenue_eur", "srp_eur", "meses_estimados"):
        cat[col] = pd.to_numeric(cat[col], errors="coerce")
    # Un SRP en 0 significa "a cotizar" (ad hoc, licencias, FTE), no gratis.
    cat["srp_eur"] = cat["srp_eur"].replace(0, np.nan)
    cat["min_revenue_eur"] = cat["min_revenue_eur"].replace(0, np.nan)

    cat["activo"] = cat["estado_catalogo"].fillna("Active").str.lower().eq("active")

    # --- capa curada: reglas por servicio ---------------------------------
    reglas_srv = pd.read_csv(dir_config / "servicios_reglas.csv")
    reglas_srv["service_name"] = _normalizar_texto(reglas_srv["service_name"])
    reglas_srv["grupo_sustitucion"] = reglas_srv["grupo_sustitucion"].fillna("").astype(str).str.strip()
    sin_regla = sorted(set(cat["service_name"]) - set(reglas_srv["service_name"]))
    if sin_regla:
        raise ValueError(
            "Servicios del catalogo ZOHO sin fila en config/servicios_reglas.csv: "
            f"{sin_regla[:10]}{'...' if len(sin_regla) > 10 else ''}. "
            "Agregalos con su label corta, grupo de sustitucion, nivel y modalidad."
        )
    cat = cat.merge(reglas_srv, on="service_name", how="left")

    # --- capa curada: regla de cada grupo ---------------------------------
    grupos = pd.read_csv(dir_config / "grupos_sustitucion.csv")
    grupos["grupo_sustitucion"] = grupos["grupo_sustitucion"].astype(str).str.strip()
    malas = set(grupos["regla_grupo"]) - REGLAS_VALIDAS
    if malas:
        raise ValueError(f"Reglas de grupo no validas en grupos_sustitucion.csv: {sorted(malas)}. "
                         f"Validas: {sorted(REGLAS_VALIDAS)}")
    sin_definir = sorted(set(cat.loc[cat["grupo_sustitucion"] != "", "grupo_sustitucion"]) - set(grupos["grupo_sustitucion"]))
    if sin_definir:
        raise ValueError(f"Grupos usados en servicios_reglas.csv pero no definidos en "
                         f"grupos_sustitucion.csv: {sin_definir}")
    cat = cat.merge(grupos, on="grupo_sustitucion", how="left")

    # Un servicio sin grupo es su propio grupo: nunca compite con nadie.
    singleton = cat["grupo_sustitucion"] == ""
    cat.loc[singleton, "grupo_sustitucion"] = "solo:" + cat.loc[singleton, "service_name"]
    cat.loc[singleton, "regla_grupo"] = "ACUMULABLE"
    cat.loc[singleton, "descripcion_regla"] = "Servicio sin sustitutos en el catalogo."
    cat["regla_grupo"] = cat["regla_grupo"].fillna("ACUMULABLE")
    cat["nivel"] = pd.to_numeric(cat["nivel"], errors="coerce").fillna(1).astype(int)
    cat["modalidad"] = cat["modalidad"].fillna("Proyecto")
    cat["es_singleton"] = singleton.values

    # Ticket tipo por terciles del precio de lista, para leer el catalogo rapido.
    srp = cat["srp_eur"]
    cortes = srp.quantile([0.33, 0.66])
    cat["ticket_tipo"] = np.where(
        srp.isna(), "A cotizar",
        np.where(srp <= cortes.iloc[0], "Bajo", np.where(srp <= cortes.iloc[1], "Medio", "Alto")),
    )
    cat["servicio_normalizado"] = cat["label_corto"]
    return cat.reset_index(drop=True)


def universo(catalogo: pd.DataFrame, servicios_con_historial: set[str]) -> pd.DataFrame:
    """Servicios que entran al mapa: los activos, mas cualquiera ya pitcheado.

    Un servicio dado de baja pero con historial se mantiene para no perder la
    lectura de lo que si se ofrecio; se marca con ``activo=False``.
    """
    dentro = catalogo["activo"] | catalogo["service_name"].isin(servicios_con_historial)
    return catalogo[dentro].copy().reset_index(drop=True)
