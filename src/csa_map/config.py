"""Carga de la configuracion declarativa del mapa.

Toda la logica de negocio parametrizable (fases, pesos del score, taxonomia de
servicios y ficha de cuentas) vive en ``config/``. Este modulo la lee y la deja
disponible como un unico objeto ``Config``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

RAIZ = Path(__file__).resolve().parents[2]
DIR_CONFIG = RAIZ / "config"
DIR_OUTPUTS = RAIZ / "outputs"


@dataclass
class Config:
    params: dict[str, Any]
    taxonomia: pd.DataFrame
    cuentas: pd.DataFrame
    raiz: Path = RAIZ

    # --- atajos de lectura -------------------------------------------------
    @property
    def fuente(self) -> dict[str, Any]:
        return self.params["fuente"]

    @property
    def fases(self) -> dict[str, dict[str, Any]]:
        return self.params["fases"]

    @property
    def scoring(self) -> dict[str, Any]:
        return self.params["scoring"]

    @property
    def pesos(self) -> dict[str, float]:
        return self.scoring["pesos"]

    def ruta_fuente(self) -> Path:
        return self.raiz / self.fuente["archivo"]


def cargar(dir_config: Path | str = DIR_CONFIG) -> Config:
    """Lee ``parametros.yaml``, la taxonomia de servicios y la ficha de cuentas."""
    dir_config = Path(dir_config)
    with (dir_config / "parametros.yaml").open(encoding="utf-8") as fh:
        params = yaml.safe_load(fh)

    taxonomia = pd.read_csv(dir_config / "taxonomia_servicios.csv")
    cuentas = pd.read_csv(dir_config / "cuentas.csv")

    pesos = params["scoring"]["pesos"]
    total = round(sum(pesos.values()), 6)
    if total != 1.0:
        raise ValueError(
            f"Los pesos del scoring deben sumar 1.0 (suman {total}). Revisa config/parametros.yaml"
        )

    for col in ("service_name", "familia", "pilar"):
        if col not in taxonomia.columns:
            raise ValueError(f"Falta la columna '{col}' en taxonomia_servicios.csv")

    duplicados = taxonomia["service_name"].duplicated()
    if duplicados.any():
        repetidos = taxonomia.loc[duplicados, "service_name"].tolist()
        raise ValueError(f"Servicios duplicados en la taxonomia: {repetidos}")

    return Config(params=params, taxonomia=taxonomia, cuentas=cuentas)
