"""Genera el libro Excel del mapa de proyectos y oportunidades.

El libro esta pensado para dos usos: leer el mapa de un vistazo (hojas 01-11)
y minar la base con tablas dinamicas (hojas 20-91).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .pipeline import Mapa

COLORES = {
    "EJEC": {"bg_color": "#1B7F5F", "font_color": "#FFFFFF"},
    "PITCH": {"bg_color": "#F0B429", "font_color": "#3D3016"},
    "PAUSA": {"bg_color": "#B9C2CC", "font_color": "#2A3038"},
    "PERD": {"bg_color": "#C6493F", "font_color": "#FFFFFF"},
}
PRIORIDAD = {
    "A": {"bg_color": "#C6493F", "font_color": "#FFFFFF", "bold": True},
    "B": {"bg_color": "#F0B429", "font_color": "#3D3016"},
    "C": {"bg_color": "#EEF1F4", "font_color": "#5A6472"},
}

LEEME = [
    ("Que es este archivo",
     "Mapa de proyectos ejecutados y prospectados por cuenta para CSA Chile, construido "
     "sobre el export de pitches del CRM. Sirve para tres cosas: ver que le vendimos a cada "
     "cliente, minar cada cuenta por familia de servicio, y detectar espacios blancos: "
     "servicios del catalogo que a esa cuenta nunca se le ofrecieron."),
    ("Unidad de analisis",
     "La celda = cruce cuenta x servicio del catalogo. Con N cuentas y M servicios el mapa "
     "tiene N x M celdas, esten o no en el CRM. Las celdas sin ningun pitch son el espacio blanco."),
    ("Estados de cobertura",
     "EJEC = ejecutado (algun pitch ganado) | PITCH = en pipeline activo (pitching, prospecting, lead) | "
     "PAUSA = on hold | PERD = se ofrecio y se perdio | vacio = NUNCA OFRECIDO (espacio blanco). "
     "Si una celda tiene varios pitches gana el estado mas alto de esa jerarquia."),
    ("Como se prioriza una oportunidad",
     "Score 0-100 = 100 x (demanda x 0.24 + afinidad x 0.26 + valor x 0.18 + momentum x 0.12 + "
     "adyacencia x 0.20), multiplicado por un factor segun el estado actual de la celda y por una "
     "penalizacion si la derrota es reciente. Los pesos se editan en config/parametros.yaml."),
    ("Demanda",
     "Que tan vendible es el servicio en el portafolio Chile: mezcla la penetracion "
     "(% de cuentas que ya lo ejecutan) con su win rate historico."),
    ("Afinidad",
     "Dos senales de mineria: market basket (que servicios se compran juntos, con confianza y lift "
     "sobre las canastas de cada cuenta) y adopcion de pares (% de cuentas de la MISMA industria que "
     "ya ejecutan el servicio). Responde a 'tus comparables ya lo compran y esta cuenta no'."),
    ("Valor",
     "Ticket mediano historico del servicio, normalizado en escala logaritmica."),
    ("Momentum",
     "Que tan vivo esta el servicio en el mercado: mezcla el % de pitches recientes con un "
     "decaimiento exponencial sobre los dias desde el ultimo movimiento."),
    ("Adyacencia",
     "Cercania al portafolio actual de la cuenta: 1.00 misma subfamilia, 0.75 misma familia, "
     "0.50 mismo pilar, 0.25 cliente activo pero cruzando de pilar, 0.10 cuenta sin nada ejecutado."),
    ("Prioridad",
     "A = score >= 48 (jugada del trimestre) | B = score >= 36 (construir el caso) | C = el resto. "
     "Son umbrales absolutos para poder comparar la evolucion trimestre a trimestre."),
    ("Como actualizarlo",
     "Reemplazar data/raw/Reporte_Pitches_CL.xlsx por el export nuevo y correr 'python run.py'. "
     "Si aparecen servicios o cuentas nuevas el pipeline se detiene y pide clasificarlos en "
     "config/taxonomia_servicios.csv y config/cuentas.csv: eso mantiene el mapa limpio en el tiempo."),
    ("Moneda", "Todos los montos estan en EUR (columna PROJECT PRICE (Lcy) del export, ya convertida)."),
]


def _escribir(writer, df: pd.DataFrame, hoja: str, ancho_max: int = 46,
              indice: bool = False, congelar: tuple[int, int] = (1, 0)) -> None:
    df.to_excel(writer, sheet_name=hoja, index=indice, startrow=0)
    ws = writer.sheets[hoja]
    wb = writer.book
    cab = wb.add_format({"bold": True, "bg_color": "#16324A", "font_color": "#FFFFFF",
                         "border": 1, "border_color": "#0E2233", "text_wrap": True, "valign": "vcenter"})
    offset = 1 if indice else 0
    if indice:
        ws.write(0, 0, df.index.name or "", cab)
    for i, col in enumerate(df.columns):
        ws.write(0, i + offset, str(col), cab)
        largo = df[col].astype(str).head(200).str.len().max()
        largo = int(largo) if pd.notna(largo) else 10
        ancho = max(len(str(col)) + 2, largo + 2)
        ws.set_column(i + offset, i + offset, min(ancho, ancho_max))
    if indice:
        largo_idx = df.index.astype(str).str.len().max()
        largo_idx = int(largo_idx) if pd.notna(largo_idx) else 12
        ws.set_column(0, 0, min(max(largo_idx + 2, 14), 34))
    ws.freeze_panes(*congelar)
    ws.autofilter(0, offset, len(df), len(df.columns) - 1 + offset)


def generar(mapa: Mapa, destino: Path | str) -> Path:
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(destino, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as writer:
        wb = writer.book

        # ---------------- 00 Leeme ----------------
        ws = wb.add_worksheet("00_Leeme")
        writer.sheets["00_Leeme"] = ws
        titulo = wb.add_format({"bold": True, "font_size": 16, "font_color": "#16324A"})
        sub = wb.add_format({"font_size": 10, "font_color": "#5A6472"})
        h = wb.add_format({"bold": True, "bg_color": "#EEF1F4", "border": 1,
                           "border_color": "#D5DBE1", "valign": "top", "text_wrap": True})
        t = wb.add_format({"border": 1, "border_color": "#D5DBE1", "valign": "top", "text_wrap": True})
        ws.set_column(0, 0, 30)
        ws.set_column(1, 1, 110)
        ws.write(0, 0, "Mapa de Proyectos y Oportunidades - CSA Chile", titulo)
        ws.write(1, 0, f"Fecha de corte: {mapa.corte:%d-%m-%Y}  |  {mapa.resumen['n_pitches']} pitches  |  "
                       f"{mapa.resumen['n_cuentas']} cuentas  |  {mapa.resumen['n_servicios_catalogo']} servicios", sub)
        fila = 3
        for k, v in LEEME:
            ws.write(fila, 0, k, h)
            ws.write(fila, 1, v, t)
            ws.set_row(fila, max(15, 13 * (len(v) // 105 + 1)))
            fila += 1

        # ---------------- 01 Resumen ----------------
        r = mapa.resumen
        resumen = pd.DataFrame(
            [
                ("Cuentas en el mapa", r["n_cuentas"], "Cuentas con al menos un pitch registrado"),
                ("Servicios en el catalogo", r["n_servicios_catalogo"], "Servicios clasificados en la taxonomia"),
                ("Celdas del mapa", r["n_celdas"], "Cuentas x servicios: el universo completo"),
                ("Celdas ejecutadas", r["n_ejecutado"], "Cruces con al menos un pitch ganado"),
                ("Celdas en pipeline", r["n_en_curso"], "Pitching, prospecting o lead"),
                ("Celdas en pausa", r["n_en_pausa"], "On hold: propuestas a destrabar"),
                ("Celdas perdidas", r["n_perdido"], "Se ofrecio y no se gano"),
                ("ESPACIOS BLANCOS", r["n_blanco"], "Nunca ofrecido a esa cuenta: el foco de este mapa"),
                ("Cobertura del catalogo", f"{r['cobertura_pct']}%", "Celdas ejecutadas sobre el total del mapa"),
                ("Win rate global", f"{r['win_rate_global']:.1%}", "Ganados / (ganados + perdidos)"),
                ("Revenue ganado (EUR)", round(r["revenue_ganado_eur"]), "Suma de pitches ganados"),
                ("Pipeline abierto (EUR)", round(r["pipeline_abierto_eur"]), "Suma de pitches vivos"),
                ("Valor perdido (EUR)", round(r["valor_perdido_eur"]), "Suma de pitches perdidos"),
                ("Oportunidades prioridad A", r["oportunidades_A"], "Score >= 48: la jugada del trimestre"),
                ("Oportunidades prioridad B", r["oportunidades_B"], "Score >= 36: construir el caso"),
                ("Valor potencial A+B (EUR)", round(r["valor_espacios_blancos_eur"]),
                 "Suma de tickets medianos de las oportunidades A y B"),
            ],
            columns=["Indicador", "Valor", "Lectura"],
        )
        _escribir(writer, resumen, "01_Resumen")

        # ---------------- 10 Mapa de cobertura ----------------
        matriz = mapa.matriz_estado.fillna("")
        _escribir(writer, matriz, "10_Mapa_Cobertura", ancho_max=14, indice=True, congelar=(1, 1))
        ws = writer.sheets["10_Mapa_Cobertura"]
        n_f, n_c = matriz.shape
        ws.set_column(1, n_c, 9)
        base_fmt = {"border": 1, "border_color": "#FFFFFF", "align": "center", "bold": True, "font_size": 8}
        for simbolo, estilo in COLORES.items():
            ws.conditional_format(1, 1, n_f, n_c, {
                "type": "cell", "criteria": "equal to", "value": f'"{simbolo}"',
                "format": wb.add_format({**base_fmt, **estilo}),
            })
        ws.conditional_format(1, 1, n_f, n_c, {
            "type": "blanks",
            "format": wb.add_format({"bg_color": "#FFFFFF", "border": 1, "border_color": "#E4E8EC"}),
        })

        # ---------------- 11 Mapa por familia ----------------
        fam = mapa.matriz_familia.fillna(0).round(1)
        _escribir(writer, fam, "11_Mapa_Familias", ancho_max=24, indice=True, congelar=(1, 1))
        ws = writer.sheets["11_Mapa_Familias"]
        ws.conditional_format(1, 1, *fam.shape, {
            "type": "3_color_scale", "min_color": "#FFFFFF",
            "mid_color": "#BFE3D4", "max_color": "#1B7F5F",
        })

        # ---------------- 20-22 Oportunidades ----------------
        cols_op = [
            "cuenta_normalizada", "industria", "tier_cuenta", "servicio_normalizado", "familia",
            "pilar", "tipo_oportunidad", "prioridad", "score", "ranking_en_cuenta",
            "valor_potencial_eur", "modelo_comercial", "ticket_tipo",
            "c_demanda", "c_afinidad", "c_valor", "c_momentum", "c_adyacencia",
            "adopcion_industria_pct", "cuentas_industria_ejecutan", "cuentas_industria",
            "basket_lift_ejecutado", "penetracion_pct", "win_rate", "momentum_pct",
            "n_pitches", "dias_desde_derrota", "reactivable", "motivo", "accion_sugerida",
        ]
        hojas_op = {
            "20_Oportunidades": mapa.oportunidades[cols_op],
            "21_Top_por_Cuenta": mapa.top_oportunidades[cols_op],
            "22_Reactivacion": mapa.oportunidades.loc[
                mapa.oportunidades["tipo_oportunidad"].isin(["Reactivacion", "Rescate (en pausa)"]), cols_op
            ],
        }
        for hoja, df in hojas_op.items():
            _escribir(writer, df.reset_index(drop=True), hoja, congelar=(1, 1))
            ws = writer.sheets[hoja]
            col_p = cols_op.index("prioridad")
            for letra, estilo in PRIORIDAD.items():
                ws.conditional_format(1, col_p, len(df), col_p, {
                    "type": "cell", "criteria": "equal to", "value": f'"{letra}"',
                    "format": wb.add_format({**estilo, "align": "center"}),
                })
            col_s = cols_op.index("score")
            ws.conditional_format(1, col_s, len(df), col_s, {
                "type": "data_bar", "bar_color": "#16324A", "bar_solid": True,
            })

        # ---------------- 30-31 Perfiles ----------------
        _escribir(writer, mapa.perfil_cuentas, "30_Perfil_Cuentas", congelar=(1, 2))
        _escribir(writer, mapa.perfil_servicios, "31_Perfil_Servicios", congelar=(1, 1))

        # ---------------- 40-41 Mineria ----------------
        reglas = pd.concat(mapa.reglas.values(), ignore_index=True)
        _escribir(writer, reglas, "40_Afinidad_Servicios")
        _escribir(writer, mapa.adopcion_industria, "41_Adopcion_Industria")

        # ---------------- 50 Pipeline ----------------
        _escribir(writer, mapa.pipeline_abierto, "50_Pipeline_Abierto")

        # ---------------- 90-91 Base ----------------
        _escribir(writer, mapa.base, "90_Base_Normalizada", congelar=(1, 2))
        cols_celdas = [
            "cuenta_normalizada", "company", "industria", "grupo_economico", "tier_cuenta",
            "servicio_normalizado", "label_corto", "service_name", "familia", "subfamilia", "pilar",
            "modelo_comercial", "ticket_tipo", "cobertura", "etiqueta_cobertura",
            "n_pitches", "n_ganados", "n_perdidos", "n_abiertos",
            "revenue_ganado_eur", "pipeline_abierto_eur", "valor_perdido_eur",
            "primer_contacto", "ultimo_movimiento", "ultima_derrota", "estados", "es_espacio_blanco",
        ]
        _escribir(writer, mapa.celdas[cols_celdas], "91_Celdas_Cuenta_Servicio", congelar=(1, 1))

    return destino
