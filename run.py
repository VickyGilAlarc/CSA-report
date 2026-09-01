#!/usr/bin/env python3
"""Construye el mapa completo: Excel + dashboard HTML.

    python run.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from csa_map import dashboard, excel_report          # noqa: E402
from csa_map.pipeline import construir               # noqa: E402

SALIDA = Path(__file__).parent / "outputs"


def main() -> int:
    mapa = construir()
    r = mapa.resumen
    print(f"Corte {r['fecha_corte']:%d-%m-%Y} | {r['n_pitches']} pitches | "
          f"{r['n_cuentas']} cuentas | {r['n_servicios_catalogo']} servicios")
    print(f"Mapa: {r['n_celdas']} celdas -> {r['n_ejecutado']} ejecutadas, "
          f"{r['n_en_curso']} en pipeline, {r['n_en_pausa']} en pausa, "
          f"{r['n_perdido']} perdidas, {r['n_blanco']} espacios blancos")
    evitadas = r["n_oportunidades_brutas"] - r["n_oportunidades_netas"]
    print(f"Sustitucion: {r['n_oportunidades_netas']} oportunidades netas "
          f"({evitadas} duplicados evitados: {r['n_alternativas']} alternativas, "
          f"{r['n_cubiertas']} cubiertas) · {r['n_upgrades']} upgrades")
    print(f"Prioridad: {r['oportunidades_A']} en A / {r['oportunidades_B']} en B")

    xlsx = excel_report.generar(mapa, SALIDA / "mapa_oportunidades_csa_cl.xlsx")
    print(f"  -> {xlsx.relative_to(Path(__file__).parent)}")

    csvs = {
        "celdas_cuenta_servicio.csv": mapa.celdas,
        "oportunidades.csv": mapa.oportunidades,
        "oportunidades_netas.csv": mapa.oportunidades_netas,
        "grupos_sustitucion.csv": mapa.grupos,
        "catalogo_universo.csv": mapa.universo,
        "perfil_cuentas.csv": mapa.perfil_cuentas,
        "perfil_servicios.csv": mapa.perfil_servicios,
        "base_normalizada.csv": mapa.base,
    }
    (SALIDA / "csv").mkdir(parents=True, exist_ok=True)
    for nombre, df in csvs.items():
        df.to_csv(SALIDA / "csv" / nombre, index=False)
    print(f"  -> outputs/csv/ ({len(csvs)} archivos)")

    html = dashboard.generar(mapa, SALIDA / "mapa_csa_cl.html")
    print(f"  -> {html.relative_to(Path(__file__).parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
