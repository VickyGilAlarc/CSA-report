"""Sustitucion entre servicios: separa oportunidad real de esfuerzo duplicado.

Tres variantes de Online Data Optimization no son tres oportunidades: con una
basta. Este modulo aplica, cuenta por cuenta y grupo por grupo, la regla que
convierte la lista cruda de celdas en **oportunidades netas**.

Cada servicio pertenece a un `grupo_sustitucion` con una `regla_grupo`:

``EXCLUSIVO``
    Los miembros son caminos alternativos para el mismo resultado (las 3 ODO,
    las 4 rutas de CAPI, los enfoques de MMM). Si la cuenta ya tiene uno, el
    resto queda **cubierto**. Si no tiene ninguno, se propone **uno solo**: el
    de mejor score. Los demas quedan como alternativas del mismo caso.

``ESCALABLE``
    Los miembros son escalones ordenados por `nivel` (C-GenIA Basic /
    Intermediate / Advanced, contrato puntual vs anual). Lo que esta al nivel
    de la cuenta o por debajo queda **cubierto**; el siguiente escalon es un
    **upgrade**, valorizado por la diferencia de precio, no por el precio total.

``ACUMULABLE``
    Los miembros son cosas distintas que suman (modelos predictivos, ad hoc de
    distintas disciplinas). Cada uno es su propia oportunidad.

El resultado es la columna `rol_en_grupo`, y con ella `oportunidad_neta`:

    UNICO         sin sustitutos: cuenta como oportunidad
    REPRESENTANTE la variante elegida del grupo: cuenta como oportunidad
    UPGRADE       siguiente escalon sobre algo ya implementado: cuenta
    ALTERNATIVA   otra variante del mismo caso: NO cuenta, se guarda como opcion
    CUBIERTO      ya resuelto por un servicio hermano: NO cuenta
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ROLES_NETOS = ("UNICO", "REPRESENTANTE", "UPGRADE")

ETIQUETA_ROL = {
    "UNICO": "Oportunidad unica",
    "REPRESENTANTE": "Variante elegida del grupo",
    "UPGRADE": "Upgrade del escalon actual",
    "ALTERNATIVA": "Alternativa equivalente",
    "CUBIERTO": "Ya cubierto por un sustituto",
}


def _resolver_grupo(miembros: pd.DataFrame, ejecutados: pd.DataFrame,
                    en_curso: pd.DataFrame, params: dict) -> list[dict]:
    """Asigna rol a cada miembro puntuable de un grupo dentro de una cuenta.

    ``ejecutados`` y ``en_curso`` son lo que esa cuenta ya tiene de ese mismo
    grupo, y son los que determinan si lo demas es upgrade, alternativa o
    trabajo ya cubierto.
    """
    regla = miembros["regla_grupo"].iloc[0]
    salida = []

    if regla == "ACUMULABLE":
        for r in miembros.itertuples():
            salida.append({"idx": r.Index, "rol": "UNICO", "cubierto_por": None,
                           "nivel_base": None, "motivo_grupo": None})
        return salida

    # --- ya hay algo implementado en el grupo -----------------------------
    if len(ejecutados):
        top = ejecutados.sort_values("nivel").iloc[-1]
        nivel_top = int(top["nivel"])
        candidatos_upgrade = miembros[miembros["nivel"] > nivel_top] if regla == "ESCALABLE" else miembros.iloc[0:0]

        siguiente = None
        elegido_upgrade = None
        if len(candidatos_upgrade) and params.get("upgrade_solo_siguiente", True):
            siguiente = int(candidatos_upgrade["nivel"].min())
            # Dentro del escalon siguiente tambien hay variantes equivalentes
            # (mensual vs anual, por ejemplo): se propone una sola.
            en_escalon = candidatos_upgrade[candidatos_upgrade["nivel"] == siguiente]
            elegido_upgrade = en_escalon.sort_values(
                ["score_base_prelim", "valor_anual_eur"], ascending=[False, False]
            ).index[0]

        for r in miembros.itertuples():
            if regla == "EXCLUSIVO" or r.nivel <= nivel_top:
                salida.append({
                    "idx": r.Index, "rol": "CUBIERTO",
                    "cubierto_por": top["servicio_normalizado"], "nivel_base": nivel_top,
                    "motivo_grupo": f"La cuenta ya implementa {top['servicio_normalizado']} "
                                    f"en el grupo {r.grupo_sustitucion}.",
                })
            elif siguiente is not None and (r.nivel > siguiente or r.Index != elegido_upgrade):
                razon = (f"Escalon mas alto que el siguiente inmediato sobre "
                         f"{top['servicio_normalizado']}." if r.nivel > siguiente
                         else f"Variante equivalente del mismo escalon de upgrade.")
                salida.append({
                    "idx": r.Index, "rol": "ALTERNATIVA",
                    "cubierto_por": top["servicio_normalizado"], "nivel_base": nivel_top,
                    "motivo_grupo": razon,
                })
            else:
                salida.append({
                    "idx": r.Index, "rol": "UPGRADE",
                    "cubierto_por": top["servicio_normalizado"], "nivel_base": nivel_top,
                    "motivo_grupo": f"Sube desde {top['servicio_normalizado']} "
                                    f"(nivel {nivel_top} a {int(r.nivel)}).",
                })
        return salida

    # --- hay una propuesta viva en el grupo -------------------------------
    if len(en_curso) and params.get("pipeline_bloquea_grupo", True):
        vivo = en_curso.sort_values("nivel").iloc[-1]
        for r in miembros.itertuples():
            salida.append({
                "idx": r.Index, "rol": "CUBIERTO",
                "cubierto_por": vivo["servicio_normalizado"], "nivel_base": None,
                "motivo_grupo": f"Hay una propuesta viva de {vivo['servicio_normalizado']} "
                                f"en el mismo grupo: no se pitchean dos variantes en paralelo.",
            })
        return salida

    # --- grupo virgen: se elige una sola variante -------------------------
    candidatos = miembros
    if regla == "ESCALABLE" and params.get("entrar_por_nivel_minimo", True):
        candidatos = miembros[miembros["nivel"] == miembros["nivel"].min()]

    ganador = candidatos.sort_values(["score_base_prelim", "valor_referencia_eur"],
                                     ascending=[False, False]).index[0]
    nombre_ganador = miembros.loc[ganador, "servicio_normalizado"]
    n = len(miembros)
    for r in miembros.itertuples():
        if r.Index == ganador:
            salida.append({
                "idx": r.Index, "rol": "REPRESENTANTE", "cubierto_por": None, "nivel_base": None,
                "motivo_grupo": (f"Variante elegida entre {n} del grupo {r.grupo_sustitucion}: "
                                 f"con una basta." if n > 1 else None),
            })
        else:
            salida.append({
                "idx": r.Index, "rol": "ALTERNATIVA", "cubierto_por": nombre_ganador, "nivel_base": None,
                "motivo_grupo": f"Misma necesidad que {nombre_ganador}: implementar ambas es "
                                f"esfuerzo duplicado.",
            })
    return salida


def asignar_roles(celdas_df: pd.DataFrame, candidatas: pd.DataFrame,
                  params: dict) -> pd.DataFrame:
    """Devuelve `candidatas` con rol_en_grupo, cubierto_por y valor de upgrade.

    ``celdas_df`` es la matriz completa (necesaria para saber que tiene la cuenta);
    ``candidatas`` son las celdas puntuables, ya con `score_base_prelim`.
    """
    ejecutadas = celdas_df[celdas_df["cobertura"] == "EJECUTADO"]
    en_curso_todas = celdas_df[celdas_df["cobertura"] == "EN_CURSO"]

    por_cuenta_grupo_ej = {k: v for k, v in ejecutadas.groupby(["company", "grupo_sustitucion"], observed=True)}
    por_cuenta_grupo_ec = {k: v for k, v in en_curso_todas.groupby(["company", "grupo_sustitucion"], observed=True)}

    vacio_ej = ejecutadas.iloc[0:0]
    vacio_ec = en_curso_todas.iloc[0:0]

    filas = []
    for clave, miembros in candidatas.groupby(["company", "grupo_sustitucion"], observed=True):
        filas.extend(_resolver_grupo(
            miembros,
            por_cuenta_grupo_ej.get(clave, vacio_ej),
            por_cuenta_grupo_ec.get(clave, vacio_ec),
            params,
        ))

    roles = pd.DataFrame(filas).set_index("idx").rename(columns={"rol": "rol_en_grupo"})
    out = candidatas.join(roles)
    out["etiqueta_rol"] = out["rol_en_grupo"].map(ETIQUETA_ROL)
    out["oportunidad_neta"] = out["rol_en_grupo"].isin(ROLES_NETOS)

    # Un upgrade se valoriza por la diferencia contra el escalon que la cuenta
    # ya tiene, no por el precio de lista completo.
    precio_actual = (
        celdas_df.set_index(["company", "servicio_normalizado"])["valor_anual_eur"]
        .groupby(level=[0, 1]).first()
    )
    claves = pd.MultiIndex.from_arrays([out["company"], out["cubierto_por"].fillna("")])
    base_actual = precio_actual.reindex(claves).to_numpy()
    delta = out["valor_anual_eur"].to_numpy() - base_actual
    es_upgrade = (out["rol_en_grupo"] == "UPGRADE").to_numpy()
    out["valor_oportunidad_eur"] = np.where(
        es_upgrade & np.isfinite(delta) & (delta > 0), delta, out["valor_anual_eur"].to_numpy()
    )
    return out


def resumen_grupos(oportunidades: pd.DataFrame) -> pd.DataFrame:
    """Cuanto esfuerzo duplicado evita el modelo, grupo por grupo."""
    con_grupo = oportunidades[~oportunidades["grupo_sustitucion"].str.startswith("solo:")]
    if con_grupo.empty:
        return pd.DataFrame(columns=["grupo_sustitucion", "regla_grupo", "descripcion_regla"])
    agg = (
        con_grupo.groupby(["grupo_sustitucion", "regla_grupo", "descripcion_regla"], observed=True)
        .agg(
            celdas=("service_name", "count"),
            cuentas=("company", "nunique"),
            netas=("oportunidad_neta", "sum"),
            alternativas=("rol_en_grupo", lambda s: (s == "ALTERNATIVA").sum()),
            cubiertas=("rol_en_grupo", lambda s: (s == "CUBIERTO").sum()),
            upgrades=("rol_en_grupo", lambda s: (s == "UPGRADE").sum()),
        )
        .reset_index()
    )
    agg["celdas_evitadas"] = agg["celdas"] - agg["netas"]
    agg["reduccion_pct"] = (agg["celdas_evitadas"] / agg["celdas"] * 100).round(1)
    return agg.sort_values("celdas_evitadas", ascending=False).reset_index(drop=True)
