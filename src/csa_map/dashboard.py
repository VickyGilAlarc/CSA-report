"""Dashboard HTML autocontenido del mapa de cuentas.

Emite un unico archivo con los datos embebidos como JSON, para que se pueda
abrir sin servidor y regenerar cada vez que llega un export nuevo del CRM.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .pipeline import Mapa

CODIGO_ESTADO = {"EJECUTADO": 1, "EN_CURSO": 2, "EN_PAUSA": 3, "PERDIDO": 4, "BLANCO": 0}


def _limpio(valor):
    if valor is None or (isinstance(valor, float) and not np.isfinite(valor)):
        return None
    if isinstance(valor, (np.integer,)):
        return int(valor)
    if isinstance(valor, (np.floating,)):
        return round(float(valor), 4)
    if isinstance(valor, (pd.Timestamp,)):
        return None if pd.isna(valor) else valor.strftime("%Y-%m-%d")
    if pd.isna(valor):
        return None
    return valor


def construir_datos(mapa: Mapa) -> dict:
    cuentas = mapa.perfil_cuentas.sort_values(
        ["industria", "cuenta_normalizada"]
    ).reset_index(drop=True)
    idx_cuenta = {c: i for i, c in enumerate(cuentas["company"])}

    servicios = mapa.perfil_servicios.sort_values(
        ["familia", "servicio_normalizado"]
    ).reset_index(drop=True)
    idx_serv = {s: i for i, s in enumerate(servicios["service_name"])}

    celdas = []
    for r in mapa.celdas.itertuples():
        celdas.append([
            idx_cuenta[r.company],
            idx_serv[r.service_name],
            CODIGO_ESTADO[str(r.cobertura)],
            int(r.n_pitches),
            round(float(r.revenue_ganado_eur)),
            _limpio(r.ultimo_movimiento),
            r.estados,
        ])

    ops = []
    for r in mapa.oportunidades.itertuples():
        ops.append({
            "c": idx_cuenta[r.company],
            "s": idx_serv[r.service_name],
            "t": r.tipo_oportunidad,
            "sc": float(r.score),
            "p": r.prioridad,
            "v": _limpio(r.valor_potencial_eur),
            "r": int(r.ranking_en_cuenta),
            "k": [float(r.c_demanda), float(r.c_afinidad), float(r.c_valor),
                  float(r.c_momentum), float(r.c_adyacencia)],
            "ad": _limpio(r.adopcion_industria_pct),
            "ai": _limpio(r.cuentas_industria_ejecutan),
            "an": _limpio(r.cuentas_industria),
            "m": r.motivo,
            "a": r.accion_sugerida,
        })

    reglas = (
        mapa.reglas["ejecutado"].assign(orden=0)
        .pipe(lambda d: pd.concat([d, mapa.reglas["ofrecido"].assign(orden=1)]))
        .sort_values(["orden", "lift", "confianza"], ascending=[True, False, False])
        .head(24)
    )

    return {
        "meta": {k: _limpio(v) for k, v in mapa.resumen.items()},
        "cuentas": [
            {
                "n": r.cuenta_normalizada, "ind": r.industria, "tier": r.tier_cuenta,
                "mad": _limpio(r.indice_madurez), "pen": _limpio(r.penetracion_catalogo_pct),
                "wr": _limpio(r.win_rate), "rev": round(float(r.revenue_ganado_eur)),
                "pip": round(float(r.pipeline_abierto_eur)),
                "per": round(float(r.valor_perdido_eur)),
                "ej": int(r.servicios_ejecutado), "cu": int(r.servicios_en_curso),
                "pa": int(r.servicios_en_pausa), "pe": int(r.servicios_perdido),
                "bl": int(r.servicios_blanco), "fam": int(r.familias_ejecutadas),
                "dias": _limpio(r.dias_sin_movimiento),
                "pt": int(r.pitches_totales), "pg": int(r.pitches_ganados),
                "pp": int(r.pitches_perdidos),
            }
            for r in cuentas.itertuples()
        ],
        "servicios": [
            {
                "n": r.servicio_normalizado, "corto": r.label_corto, "fam": r.familia, "sub": r.subfamilia,
                "pil": r.pilar, "mod": r.modelo_comercial,
                "pen": _limpio(r.penetracion_pct), "wr": _limpio(r.win_rate),
                "mom": _limpio(r.momentum_pct), "tic": _limpio(r.ticket_mediano_eur),
                "ce": int(r.cuentas_con_servicio), "cb": int(r.cuentas_blanco),
                "pit": int(r.pitches),
            }
            for r in servicios.itertuples()
        ],
        "celdas": celdas,
        "ops": ops,
        "reglas": [
            {"a": r.antecedente, "b": r.consecuente, "canasta": r.canasta,
             "n": int(r.cuentas_con_ambos), "conf": float(r.confianza),
             "lift": float(r.lift or 0)}
            for r in reglas.itertuples()
        ],
    }


def generar(mapa: Mapa, destino: Path | str) -> Path:
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    datos = json.dumps(construir_datos(mapa), ensure_ascii=False, separators=(",", ":"))
    html = PLANTILLA.replace("/*__DATOS__*/null", datos)
    destino.write_text(html, encoding="utf-8")
    return destino


PLANTILLA = r"""<title>Mapa de Cuentas CSA Chile</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root{
  color-scheme: light;
  --plane:#f4f5f7; --surface:#ffffff; --surface-2:#fafbfc; --sunken:#eef0f3;
  --ink:#10161b; --ink-2:#54616c; --ink-3:#8794a0;
  --line:#dfe3e8; --line-soft:#ecEFf2; --ring:rgba(16,22,27,.10);
  --accent:#256abf; --accent-soft:#e8f0fb; --accent-ink:#1c5cab;
  --ejec:#256abf; --curso:#eda100; --pausa:#7d8a99; --perd:#d03b3b; --blanco:transparent;
  --ejec-w:#ffffff; --curso-w:#3b2f08; --pausa-w:#ffffff; --perd-w:#ffffff;
  --seq-1:#cde2fb; --seq-2:#9ec5f4; --seq-3:#5598e7; --seq-4:#2a78d6; --seq-5:#184f95;
  --prio-a:#d03b3b; --prio-b:#eda100; --prio-c:#8794a0;
  --shadow:0 1px 2px rgba(16,22,27,.05), 0 8px 24px -14px rgba(16,22,27,.22);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme: dark;
    --plane:#0d1013; --surface:#171b1e; --surface-2:#1c2125; --sunken:#12161a;
    --ink:#f2f5f7; --ink-2:#a8b3bd; --ink-3:#77848f;
    --line:#2a3138; --line-soft:#222830; --ring:rgba(255,255,255,.10);
    --accent:#3f8ae6; --accent-soft:#17273c; --accent-ink:#8bbcf2;
    --ejec:#3f8ae6; --curso:#e0a52a; --pausa:#93a0ad; --perd:#e35f5f;
    --ejec-w:#0d1013; --curso-w:#20180a; --pausa-w:#0d1013; --perd-w:#1a0c0c;
    --seq-1:#173254; --seq-2:#1c5cab; --seq-3:#2a78d6; --seq-4:#5598e7; --seq-5:#9ec5f4;
    --prio-a:#e35f5f; --prio-b:#e0a52a; --prio-c:#77848f;
    --shadow:0 1px 2px rgba(0,0,0,.5), 0 8px 24px -14px rgba(0,0,0,.8);
  }
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --plane:#0d1013; --surface:#171b1e; --surface-2:#1c2125; --sunken:#12161a;
  --ink:#f2f5f7; --ink-2:#a8b3bd; --ink-3:#77848f;
  --line:#2a3138; --line-soft:#222830; --ring:rgba(255,255,255,.10);
  --accent:#3f8ae6; --accent-soft:#17273c; --accent-ink:#8bbcf2;
  --ejec:#3f8ae6; --curso:#e0a52a; --pausa:#93a0ad; --perd:#e35f5f;
  --ejec-w:#0d1013; --curso-w:#20180a; --pausa-w:#0d1013; --perd-w:#1a0c0c;
  --seq-1:#173254; --seq-2:#1c5cab; --seq-3:#2a78d6; --seq-4:#5598e7; --seq-5:#9ec5f4;
  --prio-a:#e35f5f; --prio-b:#e0a52a; --prio-c:#77848f;
  --shadow:0 1px 2px rgba(0,0,0,.5), 0 8px 24px -14px rgba(0,0,0,.8);
}

*{box-sizing:border-box}
body{
  margin:0; background:var(--plane); color:var(--ink);
  font-family:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size:14px; line-height:1.55; -webkit-font-smoothing:antialiased;
}
h1,h2,h3{font-family:"Archivo",system-ui,sans-serif; text-wrap:balance; margin:0; letter-spacing:-.018em}
h1{font-size:clamp(26px,3.4vw,40px); font-weight:700; line-height:1.06}
h2{font-size:19px; font-weight:600}
h3{font-size:15px; font-weight:600}
p{margin:0}
a{color:var(--accent-ink)}
.wrap{max-width:1320px; margin:0 auto; padding:0 24px 72px}
.eyebrow{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:10.5px; font-weight:500;
  letter-spacing:.16em; text-transform:uppercase; color:var(--ink-3);
}
.num{font-variant-numeric:tabular-nums}

/* ---------- header ---------- */
header.top{border-bottom:1px solid var(--line); background:var(--surface); margin-bottom:26px}
.top-in{max-width:1320px; margin:0 auto; padding:26px 24px 22px;
  display:flex; gap:24px; align-items:flex-end; justify-content:space-between; flex-wrap:wrap}
.top h1{margin:6px 0 8px}
.lede{color:var(--ink-2); max-width:64ch; font-size:14.5px}
.stamp{
  font-family:"IBM Plex Mono",monospace; font-size:11px; color:var(--ink-2);
  border:1px solid var(--line); border-radius:6px; padding:9px 12px; background:var(--surface-2);
  white-space:nowrap; line-height:1.7;
}
.stamp b{color:var(--ink); font-weight:600}

/* ---------- stat strip ---------- */
.stats{display:grid; grid-template-columns:repeat(auto-fit,minmax(158px,1fr)); gap:1px;
  background:var(--line); border:1px solid var(--line); border-radius:10px; overflow:hidden; margin-bottom:34px}
.stat{background:var(--surface); padding:14px 16px 15px; display:flex; flex-direction:column; gap:3px}
.stat .k{font-family:"IBM Plex Mono",monospace; font-size:10px; letter-spacing:.13em;
  text-transform:uppercase; color:var(--ink-3)}
.stat .v{font-family:"Archivo",sans-serif; font-size:27px; font-weight:700; line-height:1.1; letter-spacing:-.02em}
.stat .s{font-size:11.5px; color:var(--ink-2); line-height:1.35}
.stat.hero{background:var(--accent-soft)}
.stat.hero .v{color:var(--accent-ink)}

/* ---------- sections ---------- */
section{margin-bottom:38px; scroll-margin-top:16px}
.sec-head{display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; margin-bottom:4px}
.sec-note{color:var(--ink-2); font-size:13px; max-width:78ch; margin-bottom:14px}
.card{background:var(--surface); border:1px solid var(--line); border-radius:10px; box-shadow:var(--shadow)}
.pad{padding:16px 18px}

/* ---------- controls ---------- */
.controls{display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin-bottom:12px}
select,input[type=search]{
  font:inherit; font-size:12.5px; color:var(--ink); background:var(--surface);
  border:1px solid var(--line); border-radius:6px; padding:6px 9px; min-width:130px;
}
input[type=search]{min-width:210px}
select:focus-visible,input:focus-visible,button:focus-visible,.cell:focus-visible,.acct-row:focus-visible{
  outline:2px solid var(--accent); outline-offset:2px}
.seg{display:inline-flex; border:1px solid var(--line); border-radius:6px; overflow:hidden}
.seg button{
  font:inherit; font-size:12px; font-weight:500; padding:6px 11px; border:0; cursor:pointer;
  background:var(--surface); color:var(--ink-2); border-right:1px solid var(--line);
}
.seg button:last-child{border-right:0}
.seg button[aria-pressed=true]{background:var(--accent); color:#fff}

/* ---------- legend ---------- */
.legend{display:flex; gap:16px; flex-wrap:wrap; align-items:center; margin:2px 0 12px;
  font-size:12px; color:var(--ink-2)}
.legend .item{display:flex; gap:7px; align-items:center}
.swatch{width:16px; height:16px; border-radius:3px; display:inline-block; position:relative; flex:none}

/* ---------- coverage matrix ---------- */
.matrix-scroll{overflow:auto; max-height:min(76vh,780px); border-radius:10px}
table.matrix{border-collapse:separate; border-spacing:0; font-size:12px}
table.matrix th,table.matrix td{padding:0; margin:0}
.mx-corner{position:sticky; left:0; top:0; z-index:6; background:var(--surface);
  border-right:1px solid var(--line); border-bottom:1px solid var(--line); min-width:190px}
.mx-fam{position:sticky; top:0; z-index:4; background:var(--surface-2); color:var(--ink-2);
  font-family:"IBM Plex Mono",monospace; font-size:9.5px; letter-spacing:.1em; text-transform:uppercase;
  font-weight:600; padding:7px 8px 6px !important; text-align:left; white-space:nowrap;
  border-bottom:1px solid var(--line); border-left:2px solid var(--line)}
.mx-svc{position:sticky; top:27px; z-index:4; background:var(--surface); height:176px; vertical-align:bottom;
  border-bottom:1px solid var(--line); border-left:1px solid var(--line-soft)}
.mx-svc.fam-start{border-left:2px solid var(--line)}
.mx-svc span{
  display:block; writing-mode:vertical-rl; transform:rotate(180deg);
  font-size:11px; color:var(--ink-2); font-weight:500; padding:0 0 8px 0; margin:0 auto;
  max-height:166px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}
.mx-acct{position:sticky; left:0; z-index:3; background:var(--surface); text-align:left;
  border-right:1px solid var(--line); border-bottom:1px solid var(--line-soft);
  padding:0 10px 0 11px !important; min-width:190px; max-width:190px; cursor:pointer}
.mx-acct .an{display:block; font-weight:500; font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
.mx-acct .ai{display:block; font-size:10px; color:var(--ink-3); white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
.mx-acct:hover,.mx-acct.on{background:var(--accent-soft)}
.mx-ind{background:var(--sunken); font-family:"IBM Plex Mono",monospace; font-size:9.5px;
  letter-spacing:.12em; text-transform:uppercase; color:var(--ink-3); font-weight:600;
  padding:6px 11px !important; text-align:left; position:sticky; left:0; z-index:3;
  border-bottom:1px solid var(--line); border-right:1px solid var(--line)}
.mx-ind-fill{background:var(--sunken); border-bottom:1px solid var(--line)}
td.cellwrap{border-bottom:1px solid var(--line-soft); border-left:1px solid var(--line-soft); background:var(--surface)}
td.cellwrap.fam-start{border-left:2px solid var(--line)}
.cell{width:26px; height:26px; display:block; margin:0 auto; border:0; padding:0; cursor:pointer;
  background:transparent; position:relative}
.cell i{position:absolute; inset:3px; border-radius:3px; display:block}
.cell[data-e="0"] i{background:transparent}
.cell[data-e="1"] i{background:var(--ejec)}
.cell[data-e="2"] i{background:var(--curso)}
.cell[data-e="3"] i{background:transparent; border:2.5px solid var(--pausa)}
.cell[data-e="4"] i{background:var(--perd)}
/* codificacion secundaria: cada estado trae su propia marca, no solo color */
.cell[data-e="2"] i::after{content:""; position:absolute; inset:0; border-radius:2px;
  background:repeating-linear-gradient(45deg,transparent 0 2px,rgba(0,0,0,.34) 2px 4px)}
.cell[data-e="4"] i::after{content:""; position:absolute; inset:0;
  background:
    linear-gradient(45deg,transparent calc(50% - .9px),var(--perd-w) calc(50% - .9px) calc(50% + .9px),transparent calc(50% + .9px)),
    linear-gradient(-45deg,transparent calc(50% - .9px),var(--perd-w) calc(50% - .9px) calc(50% + .9px),transparent calc(50% + .9px))}
.cell[data-e="1"] i::after{content:""; position:absolute; left:50%; top:50%; width:7px; height:7px;
  transform:translate(-50%,-50%); border-radius:50%; background:var(--ejec-w); opacity:.92}
.cell:hover i{outline:2px solid var(--ink); outline-offset:1px}
.cell.dim{opacity:.16}
.swatch[data-e="0"]{border:1px dashed var(--ink-3); background:var(--surface)}
.swatch[data-e="1"]{background:var(--ejec)}
.swatch[data-e="2"]{background:var(--curso); background-image:repeating-linear-gradient(45deg,transparent 0 2px,rgba(0,0,0,.34) 2px 4px)}
.swatch[data-e="3"]{border:2.5px solid var(--pausa)}
.swatch[data-e="4"]{background:var(--perd)}
.swatch[data-e="1"]::after{content:""; position:absolute; left:50%; top:50%; width:5px; height:5px;
  transform:translate(-50%,-50%); border-radius:50%; background:var(--ejec-w)}
.swatch[data-e="4"]::after{content:"\00d7"; position:absolute; inset:0; color:var(--perd-w);
  font-size:13px; line-height:16px; text-align:center; font-weight:700}

/* ---------- tooltip ---------- */
#tip{position:fixed; z-index:60; pointer-events:none; opacity:0; transition:opacity .1s;
  background:var(--surface); border:1px solid var(--line); border-radius:8px; box-shadow:var(--shadow);
  padding:9px 11px; font-size:12px; max-width:280px; line-height:1.45}
#tip.on{opacity:1}
#tip .t{font-weight:600; font-size:12.5px; margin-bottom:2px}
#tip .m{color:var(--ink-2); font-size:11.5px}
#tip .st{font-family:"IBM Plex Mono",monospace; font-size:10px; letter-spacing:.1em;
  text-transform:uppercase; margin-top:5px; display:inline-block}

/* ---------- account panel ---------- */
.acct{display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.45fr); gap:1px; background:var(--line)}
@media (max-width:920px){.acct{grid-template-columns:minmax(0,1fr)}}
.acct > div{background:var(--surface); padding:16px 18px}
.kv{display:grid; grid-template-columns:auto 1fr; gap:5px 14px; font-size:12.5px; margin-top:10px}
.kv dt{color:var(--ink-3); white-space:nowrap}
.kv dd{margin:0; font-weight:500; font-variant-numeric:tabular-nums}
.chiprow{display:flex; flex-wrap:wrap; gap:6px; margin-top:10px}
.chip{font-size:11.5px; padding:3px 9px; border-radius:20px; border:1px solid var(--line);
  background:var(--surface-2); color:var(--ink-2)}
.chip.ok{border-color:var(--ejec); color:var(--accent-ink); background:var(--accent-soft); font-weight:500}
.oplist{list-style:none; margin:10px 0 0; padding:0; display:flex; flex-direction:column; gap:9px}
.oplist li{border:1px solid var(--line); border-radius:8px; padding:10px 12px; background:var(--surface-2)}
.op-h{display:flex; align-items:center; gap:9px; flex-wrap:wrap}
.op-h .nm{font-weight:600; font-size:13px}
.op-h .fm{font-size:11px; color:var(--ink-3)}
.op-h .sc{margin-left:auto; font-family:"IBM Plex Mono",monospace; font-size:12px;
  font-weight:600; color:var(--ink-2); font-variant-numeric:tabular-nums; flex:none}
.op-m{font-size:12px; color:var(--ink-2); margin-top:4px}
.op-a{font-size:11.5px; margin-top:5px; color:var(--accent-ink); font-weight:500}
.pill{font-family:"IBM Plex Mono",monospace; font-size:10px; font-weight:600; letter-spacing:.06em;
  padding:2px 7px; border-radius:4px; color:#fff; flex:none}
.pill.A{background:var(--prio-a)} .pill.B{background:var(--prio-b); color:#332608} .pill.C{background:var(--prio-c)}
.scorebar{height:5px; border-radius:3px; background:var(--sunken); overflow:hidden; margin-top:7px}
.scorebar i{display:block; height:100%; background:var(--accent); border-radius:3px}

/* ---------- tables ---------- */
.tbl-scroll{overflow-x:auto}
table.data{width:100%; border-collapse:collapse; font-size:12.5px}
table.data th{
  text-align:left; font-family:"IBM Plex Mono",monospace; font-size:9.5px; letter-spacing:.11em;
  text-transform:uppercase; color:var(--ink-3); font-weight:600; padding:8px 10px;
  border-bottom:1px solid var(--line); position:sticky; top:0; background:var(--surface); white-space:nowrap}
table.data td{padding:8px 10px; border-bottom:1px solid var(--line-soft); vertical-align:top}
table.data tbody tr:hover{background:var(--surface-2)}
table.data td.n{text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap}
.bar{position:relative; display:block; width:100%; min-width:80px; height:16px;
  background:var(--sunken); border-radius:3px; overflow:hidden}
.bar i{position:absolute; left:0; top:0; bottom:0; border-radius:3px; background:var(--accent)}
.bar b{position:absolute; right:5px; top:0; font-size:10.5px; line-height:16px; font-weight:600;
  color:var(--ink-2); font-variant-numeric:tabular-nums}
.muted{color:var(--ink-2)}
.count{font-family:"IBM Plex Mono",monospace; font-size:11px; color:var(--ink-3)}

/* ---------- catalogo ---------- */
.cat{display:flex; flex-direction:column; gap:1px; background:var(--line)}
.cat-row{background:var(--surface); display:grid; grid-template-columns:minmax(150px,1.25fr) minmax(120px,2fr) 88px 78px;
  gap:12px; align-items:center; padding:7px 16px; font-size:12.5px}
@media (max-width:700px){.cat-row{grid-template-columns:minmax(0,1fr) minmax(0,1.4fr); }.cat-row .hidesm{display:none}}
.cat-row .nm{font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap}
.cat-row .nm small{display:block; font-weight:400; color:var(--ink-3); font-size:10.5px}
.stackbar{display:flex; height:14px; border-radius:3px; overflow:hidden; background:var(--sunken); gap:2px}
.stackbar i{display:block; height:100%}
.stackbar i.e{background:var(--ejec)} .stackbar i.c{background:var(--curso)}
.stackbar i.p{background:var(--perd)} .stackbar i.b{background:var(--sunken)}

/* ---------- method ---------- */
.method{display:grid; grid-template-columns:repeat(auto-fit,minmax(215px,1fr)); gap:1px; background:var(--line)}
.method > div{background:var(--surface); padding:14px 16px}
.method .w{font-family:"Archivo",sans-serif; font-size:22px; font-weight:700; color:var(--accent-ink)}
.method h3{margin:2px 0 4px}
.method p{font-size:12px; color:var(--ink-2)}
.formula{font-family:"IBM Plex Mono",monospace; font-size:12px; background:var(--sunken);
  border:1px solid var(--line); border-radius:8px; padding:12px 14px; overflow-x:auto;
  white-space:nowrap; color:var(--ink-2); margin-bottom:14px}
footer{border-top:1px solid var(--line); padding-top:18px; color:var(--ink-3); font-size:12px}
@media (prefers-reduced-motion:reduce){*{transition:none !important; animation:none !important}}
</style>

<header class="top">
  <div class="top-in">
    <div>
      <div class="eyebrow" id="eyebrow"></div>
      <h1>Mapa de cuentas CSA Chile</h1>
      <p class="lede">Qué le vendimos a cada cliente, qué está vivo y —sobre todo— qué del catálogo
      nunca le ofrecimos. Cada celda vacía del mapa es un espacio blanco con nombre y apellido.</p>
    </div>
    <div class="stamp" id="stamp"></div>
  </div>
</header>

<div class="wrap">
  <div class="stats" id="stats"></div>

  <section id="mapa">
    <div class="sec-head"><h2>El mapa</h2><span class="eyebrow">Cuenta × servicio</span></div>
    <p class="sec-note">Cada fila es una cuenta, cada columna un servicio del catálogo, agrupado por familia.
      El estado de la celda resuelve por jerarquía cuando hay varios pitches: ejecutado gana sobre pipeline,
      pipeline sobre pausa, pausa sobre perdido. Clic en una celda o en una cuenta abre su ficha.</p>
    <div class="controls">
      <select id="f-ind" aria-label="Filtrar por industria"></select>
      <select id="f-fam" aria-label="Filtrar por familia de servicio"></select>
      <div class="seg" role="group" aria-label="Ordenar cuentas">
        <button data-sort="ind" aria-pressed="true">Por industria</button>
        <button data-sort="mad" aria-pressed="false">Por madurez</button>
        <button data-sort="bl" aria-pressed="false">Por espacios blancos</button>
      </div>
    </div>
    <div class="legend" id="legend"></div>
    <div class="card matrix-scroll"><table class="matrix" id="matrix"></table></div>
  </section>

  <section id="ficha">
    <div class="sec-head"><h2>Ficha de cuenta</h2><span class="eyebrow">Minería por cliente</span></div>
    <p class="sec-note">El portafolio que la cuenta ya tiene, y las jugadas que el modelo pone arriba
      con el motivo por el que suben.</p>
    <div class="controls"><select id="f-cta" aria-label="Elegir cuenta"></select></div>
    <div class="card acct" id="acct"></div>
  </section>

  <section id="blancos">
    <div class="sec-head"><h2>Espacios blancos priorizados</h2><span class="eyebrow">Score 0–100</span></div>
    <p class="sec-note">Todo cruce cuenta × servicio que no está ejecutado ni en conversación, ordenado por score.
      «Espacio blanco» = nunca ofrecido. «Reactivación» = se ofreció y se perdió hace más de 9 meses.
      «Rescate» = quedó en pausa.</p>
    <div class="controls">
      <input type="search" id="q" placeholder="Buscar cuenta o servicio…" aria-label="Buscar">
      <select id="f-prio" aria-label="Filtrar por prioridad"></select>
      <select id="f-tipo" aria-label="Filtrar por tipo de oportunidad"></select>
      <select id="f-fam2" aria-label="Filtrar por familia"></select>
      <span class="count" id="op-count"></span>
    </div>
    <div class="card tbl-scroll"><table class="data" id="op-tbl"></table></div>
  </section>

  <section id="catalogo">
    <div class="sec-head"><h2>Radiografía del catálogo</h2><span class="eyebrow">Dónde hay cancha</span></div>
    <p class="sec-note">Cuántas cuentas están en cada estado para cada servicio. Lo que queda en gris
      es mercado sin tocar: cuanto más gris, más cancha hay.</p>
    <div class="legend" id="cat-legend"></div>
    <div class="card cat" id="cat"></div>
  </section>

  <section id="afinidad">
    <div class="sec-head"><h2>Qué se compra junto</h2><span class="eyebrow">Market basket</span></div>
    <p class="sec-note">Reglas «quien tiene A también tiene B» sobre las canastas de cada cuenta.
      El lift indica cuánto más probable es B cuando ya existe A, comparado con su base.
      Es la señal que alimenta el componente de afinidad del score.</p>
    <div class="card tbl-scroll"><table class="data" id="reg-tbl"></table></div>
  </section>

  <section id="metodo">
    <div class="sec-head"><h2>Cómo se calcula el score</h2><span class="eyebrow">Metodología</span></div>
    <div class="formula">score = 100 × (0.24·demanda + 0.26·afinidad + 0.18·valor + 0.12·momentum + 0.20·adyacencia) × factor_estado × factor_recencia</div>
    <div class="card method" id="method"></div>
  </section>

  <footer>
    <p id="foot"></p>
  </footer>
</div>
<div id="tip" role="tooltip"></div>

<script>
const D = /*__DATOS__*/null;
const EST = ["Nunca ofrecido","Ejecutado","En pipeline","En pausa","Ofrecido y perdido"];
const $ = (s)=>document.querySelector(s);
const $$ = (s)=>document.querySelector(s) || {set innerHTML(v){}, set textContent(v){}, addEventListener(){}};
const eur = (v)=> v==null ? "—" : "€" + Math.round(v).toLocaleString("es-CL");
const pct = (v)=> v==null ? "—" : (v*100).toFixed(0)+"%";
const esc = (s)=> String(s??"").replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

/* indice de celdas y oportunidades */
const cellByKey = new Map();
D.celdas.forEach(c => cellByKey.set(c[0]+"|"+c[1], c));
const opByKey = new Map();
D.ops.forEach(o => opByKey.set(o.c+"|"+o.s, o));
const opsByAcct = {};
D.ops.forEach(o => (opsByAcct[o.c] = opsByAcct[o.c] || []).push(o));
Object.values(opsByAcct).forEach(a => a.sort((x,y)=>y.sc-x.sc));

/* ---------- header + stats ---------- */
const M = D.meta;
$("#eyebrow").textContent = "CSA Chile · Reporte de pitches";
$("#stamp").innerHTML =
  `Corte <b>${esc(M.fecha_corte)}</b><br>${M.n_pitches} pitches · ${M.n_cuentas} cuentas · ${M.n_servicios_catalogo} servicios<br>`
  + `Fuente: Reporte_Pitches_CL.xlsx`;
$("#foot").innerHTML = `Generado desde <code>data/raw/Reporte_Pitches_CL.xlsx</code> con <code>python run.py</code>. `
  + `Montos en EUR. Los pesos del score y la taxonomía de servicios se editan en <code>config/</code>.`;

$("#stats").innerHTML = [
  ["Espacios blancos", M.n_blanco, `de ${M.n_celdas} cruces posibles`, true],
  ["Cobertura", M.cobertura_pct+"%", `${M.n_ejecutado} celdas ejecutadas`],
  ["En pipeline", M.n_en_curso, `+ ${M.n_en_pausa} en pausa por destrabar`],
  ["Perdidas", M.n_perdido, `${eur(M.valor_perdido_eur)} no convertidos`],
  ["Win rate", (M.win_rate_global*100).toFixed(0)+"%", `${eur(M.revenue_ganado_eur)} ganados`],
  ["Prioridad A", M.oportunidades_A, `+${M.oportunidades_B} en B · ${eur(M.valor_espacios_blancos_eur)} potenciales`],
].map(([k,v,s,hero])=>`<div class="stat${hero?" hero":""}"><span class="k">${k}</span>`
  + `<span class="v num">${typeof v==="number"?v.toLocaleString("es-CL"):v}</span><span class="s">${s}</span></div>`).join("");

/* ---------- legend ---------- */
$("#legend").innerHTML = [1,2,3,4,0].map(e =>
  `<span class="item"><span class="swatch" data-e="${e}"></span>${EST[e]}</span>`).join("");
$$("#cat-legend").innerHTML = [
  ["var(--ejec)","Ya lo ejecutan"],["var(--curso)","En conversación"],
  ["var(--perd)","Lo perdieron"],["var(--sunken)","Nunca ofrecido"],
].map(([c,l])=>`<span class="item"><span class="swatch" style="background:${c}"></span>${l}</span>`).join("");

/* ---------- filtros ---------- */
const industrias = [...new Set(D.cuentas.map(c=>c.ind))].sort();
const familias = [...new Set(D.servicios.map(s=>s.fam))].sort();
const opt = (v,l)=>`<option value="${esc(v)}">${esc(l)}</option>`;
$("#f-ind").innerHTML = opt("","Todas las industrias") + industrias.map(i=>opt(i,i)).join("");
$("#f-fam").innerHTML = opt("","Todas las familias") + familias.map(f=>opt(f,f)).join("");
$("#f-fam2").innerHTML = opt("","Todas las familias") + familias.map(f=>opt(f,f)).join("");
$("#f-prio").innerHTML = opt("","Toda prioridad") + ["A","B","C"].map(p=>opt(p,"Prioridad "+p)).join("");
$("#f-tipo").innerHTML = opt("","Todo tipo") + [...new Set(D.ops.map(o=>o.t))].map(t=>opt(t,t)).join("");
$("#f-cta").innerHTML = D.cuentas.map((c,i)=>opt(i,c.n+" · "+c.ind)).join("");

let orden = "ind", sel = 0;

/* ---------- matriz ---------- */
function ordenCuentas(){
  const idx = D.cuentas.map((c,i)=>i);
  if(orden==="mad") return idx.sort((a,b)=>D.cuentas[b].mad-D.cuentas[a].mad);
  if(orden==="bl")  return idx.sort((a,b)=>D.cuentas[b].bl-D.cuentas[a].bl || D.cuentas[b].mad-D.cuentas[a].mad);
  return idx.sort((a,b)=> D.cuentas[a].ind.localeCompare(D.cuentas[b].ind) || D.cuentas[a].n.localeCompare(D.cuentas[b].n));
}
function pintarMatriz(){
  const fInd = $("#f-ind").value, fFam = $("#f-fam").value;
  const cols = D.servicios.map((s,i)=>i).filter(i=>!fFam || D.servicios[i].fam===fFam);
  const filas = ordenCuentas().filter(i=>!fInd || D.cuentas[i].ind===fInd);

  // encabezado de familias (colspan) + encabezado de servicios
  let famRow = '<tr><th class="mx-corner" rowspan="2"><div style="padding:8px 11px" class="eyebrow">Cuenta</div></th>';
  let k = 0;
  while(k < cols.length){
    const fam = D.servicios[cols[k]].fam; let n = 0;
    while(k+n < cols.length && D.servicios[cols[k+n]].fam === fam) n++;
    famRow += `<th class="mx-fam" colspan="${n}">${esc(fam)}</th>`; k += n;
  }
  famRow += "</tr>";

  let svcRow = "<tr>";
  let prevFam = null;
  cols.forEach(i=>{
    const s = D.servicios[i], start = s.fam !== prevFam; prevFam = s.fam;
    svcRow += `<th class="mx-svc${start?" fam-start":""}" title="${esc(s.n)}"><span>${esc(s.corto)}</span></th>`;
  });
  svcRow += "</tr>";

  let body = "", indPrev = null;
  filas.forEach(ci=>{
    const c = D.cuentas[ci];
    if(orden==="ind" && c.ind !== indPrev){
      indPrev = c.ind;
      body += `<tr><th class="mx-ind">${esc(c.ind)}</th><td class="mx-ind-fill" colspan="${cols.length}"></td></tr>`;
    }
    body += `<tr><th class="mx-acct" tabindex="0" data-c="${ci}">`
      + `<span class="an">${esc(c.n)}</span><span class="ai">${c.ej} ejec · ${c.bl} en blanco</span></th>`;
    prevFam = null;
    cols.forEach(si=>{
      const s = D.servicios[si], start = s.fam !== prevFam; prevFam = s.fam;
      const cell = cellByKey.get(ci+"|"+si), e = cell ? cell[2] : 0;
      body += `<td class="cellwrap${start?" fam-start":""}">`
        + `<button class="cell" data-e="${e}" data-c="${ci}" data-s="${si}" tabindex="-1"`
        + ` aria-label="${esc(c.n)} — ${esc(s.n)}: ${EST[e]}"><i></i></button></td>`;
    });
    body += "</tr>";
  });
  $("#matrix").innerHTML = "<thead>"+famRow+svcRow+"</thead><tbody>"+body+"</tbody>";
  marcarSeleccion();
}
function marcarSeleccion(){
  document.querySelectorAll(".mx-acct").forEach(el=>el.classList.toggle("on", +el.dataset.c===sel));
}

/* ---------- tooltip ---------- */
const tip = $("#tip");
function mostrarTip(ev, html){
  tip.innerHTML = html; tip.classList.add("on");
  const r = tip.getBoundingClientRect();
  let x = ev.clientX + 14, y = ev.clientY + 14;
  if(x + r.width > innerWidth - 10) x = ev.clientX - r.width - 14;
  if(y + r.height > innerHeight - 10) y = ev.clientY - r.height - 14;
  tip.style.left = x+"px"; tip.style.top = y+"px";
}
document.addEventListener("mousemove", ev=>{
  const btn = ev.target.closest(".cell");
  if(!btn){ tip.classList.remove("on"); return; }
  const ci = +btn.dataset.c, si = +btn.dataset.s;
  const c = D.cuentas[ci], s = D.servicios[si];
  const cell = cellByKey.get(ci+"|"+si), e = cell ? cell[2] : 0;
  const op = opByKey.get(ci+"|"+si);
  let extra = "";
  if(e===1) extra = `<div class="m">${cell[3]} pitch(es) · ${eur(cell[4])} ganados</div>`;
  else if(cell && cell[3]>0) extra = `<div class="m">${cell[3]} pitch(es) · último movimiento ${cell[5]??"—"}</div>`;
  if(op) extra += `<div class="m">Score ${op.sc.toFixed(1)} · prioridad ${op.p} · ticket ref. ${eur(op.v)}</div>`
    + `<div class="m">${esc(op.m)}</div>`;
  mostrarTip(ev, `<div class="t">${esc(c.n)} — ${esc(s.n)}</div>`
    + `<div class="m">${esc(s.fam)}</div>`
    + `<span class="st" style="color:var(--ink-3)">${EST[e]}</span>${extra}`);
});

/* ---------- ficha de cuenta ---------- */
function pintarFicha(){
  const c = D.cuentas[sel];
  const ejecutados = D.celdas.filter(x=>x[0]===sel && x[2]===1)
    .map(x=>D.servicios[x[1]]).sort((a,b)=>a.fam.localeCompare(b.fam));
  const enCurso = D.celdas.filter(x=>x[0]===sel && x[2]===2).map(x=>D.servicios[x[1]]);
  const tot = c.ej + c.cu + c.pa + c.pe + c.bl;
  const ops = (opsByAcct[sel]||[]).slice(0,6);

  const famCob = {};
  D.celdas.filter(x=>x[0]===sel).forEach(x=>{
    const f = D.servicios[x[1]].fam;
    famCob[f] = famCob[f] || {t:0,e:0};
    famCob[f].t++; if(x[2]===1) famCob[f].e++;
  });

  $("#acct").innerHTML = `
    <div>
      <div class="eyebrow">${esc(c.ind)} · ${esc(c.tier)}</div>
      <h3 style="font-size:20px;margin-top:4px">${esc(c.n)}</h3>
      <dl class="kv">
        <dt>Índice de madurez</dt><dd>${c.mad} / 100</dd>
        <dt>Cobertura del catálogo</dt><dd>${c.pen}% · ${c.ej} de ${tot} servicios</dd>
        <dt>Win rate</dt><dd>${c.wr==null?"—":pct(c.wr)} · ${c.pg}G / ${c.pp}P de ${c.pt} pitches</dd>
        <dt>Revenue ganado</dt><dd>${eur(c.rev)}</dd>
        <dt>Pipeline abierto</dt><dd>${eur(c.pip)}</dd>
        <dt>Valor perdido</dt><dd>${eur(c.per)}</dd>
        <dt>Sin movimiento</dt><dd>${c.dias==null?"—":c.dias+" días"}</dd>
        <dt>Espacios blancos</dt><dd>${c.bl} servicios nunca ofrecidos</dd>
      </dl>
      <div class="eyebrow" style="margin-top:16px">Portafolio ejecutado</div>
      <div class="chiprow">${ejecutados.length
        ? ejecutados.map(s=>`<span class="chip ok">${esc(s.n)}</span>`).join("")
        : '<span class="chip">Sin servicios ejecutados aún</span>'}</div>
      ${enCurso.length ? `<div class="eyebrow" style="margin-top:14px">En pipeline</div>
        <div class="chiprow">${enCurso.map(s=>`<span class="chip">${esc(s.n)}</span>`).join("")}</div>` : ""}
      <div class="eyebrow" style="margin-top:16px">Cobertura por familia</div>
      <div style="margin-top:8px;display:flex;flex-direction:column;gap:5px">
        ${Object.entries(famCob).sort((a,b)=>b[1].e-a[1].e||a[0].localeCompare(b[0])).map(([f,v])=>
          `<div style="display:grid;grid-template-columns:minmax(0,1fr) 88px 34px;gap:9px;align-items:center;font-size:11.5px">
            <span class="muted" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(f)}</span>
            <span class="bar"><i style="width:${(v.e/v.t*100).toFixed(0)}%"></i></span>
            <span class="num muted" style="font-size:11px">${v.e}/${v.t}</span>
          </div>`).join("")}
      </div>
    </div>
    <div>
      <div class="eyebrow">Jugadas priorizadas</div>
      <ul class="oplist">${ops.map(o=>{
        const s = D.servicios[o.s];
        return `<li>
          <div class="op-h"><span class="pill ${o.p}">${o.p}</span>
            <span class="nm">${esc(s.n)}</span>
            <span class="fm">${esc(s.fam)} · ${esc(o.t)} · ticket ref. ${eur(o.v)}</span>
            <span class="sc">${o.sc.toFixed(1)}</span></div>
          <div class="scorebar"><i style="width:${Math.min(100,o.sc)}%"></i></div>
          <div class="op-m">${esc(o.m)}</div>
          <div class="op-a">→ ${esc(o.a)}</div>
        </li>`;}).join("")}</ul>
    </div>`;
}

/* ---------- tabla de oportunidades ---------- */
function pintarOps(){
  const q = $("#q").value.trim().toLowerCase();
  const fp = $("#f-prio").value, ft = $("#f-tipo").value, ff = $("#f-fam2").value;
  const filas = D.ops.filter(o=>{
    const c = D.cuentas[o.c], s = D.servicios[o.s];
    if(fp && o.p!==fp) return false;
    if(ft && o.t!==ft) return false;
    if(ff && s.fam!==ff) return false;
    if(q && !(c.n.toLowerCase().includes(q) || s.n.toLowerCase().includes(q)
      || c.ind.toLowerCase().includes(q) || s.fam.toLowerCase().includes(q))) return false;
    return true;
  }).sort((a,b)=>b.sc-a.sc);

  $("#op-count").textContent = `${filas.length} oportunidades · mostrando ${Math.min(120,filas.length)}`;
  const head = `<thead><tr><th>Prio</th><th>Score</th><th>Cuenta</th><th>Servicio</th>
    <th>Familia</th><th>Tipo</th><th class="n">Ticket ref.</th><th>Por qué</th><th>Acción</th></tr></thead>`;
  const body = filas.slice(0,120).map(o=>{
    const c = D.cuentas[o.c], s = D.servicios[o.s];
    return `<tr>
      <td><span class="pill ${o.p}">${o.p}</span></td>
      <td style="min-width:96px"><span class="bar"><i style="width:${Math.min(100,o.sc)}%"></i><b>${o.sc.toFixed(1)}</b></span></td>
      <td><b>${esc(c.n)}</b><br><span class="count">${esc(c.ind)}</span></td>
      <td>${esc(s.n)}</td>
      <td class="muted">${esc(s.fam)}</td>
      <td class="muted">${esc(o.t)}</td>
      <td class="n">${eur(o.v)}</td>
      <td class="muted" style="min-width:270px">${esc(o.m)}</td>
      <td class="muted" style="min-width:170px">${esc(o.a)}</td>
    </tr>`;}).join("");
  $("#op-tbl").innerHTML = head + "<tbody>" + body + "</tbody>";
}

/* ---------- catalogo ---------- */
(function pintarCatalogo(){
  const n = D.cuentas.length;
  const conteo = D.servicios.map((s,i)=>{
    const c = {e:0,c:0,p:0,x:0,b:0};
    D.celdas.filter(x=>x[1]===i).forEach(x=>{
      if(x[2]===1) c.e++; else if(x[2]===2||x[2]===3) c.c++; else if(x[2]===4) c.p++; else c.b++;
    });
    return {s,c,i};
  }).sort((a,b)=> (b.c.e+b.c.c+b.c.p) - (a.c.e+a.c.c+a.c.p) || b.s.tic-a.s.tic);

  $("#cat").innerHTML = conteo.map(({s,c})=>`
    <div class="cat-row">
      <span class="nm">${esc(s.n)}<small>${esc(s.fam)} · ${esc(s.pil).replace("CSA - ","")}</small></span>
      <span class="stackbar" title="${c.e} ejecutan · ${c.c} en conversación · ${c.p} perdieron · ${c.b} nunca ofrecido">
        ${c.e?`<i class="e" style="width:${c.e/n*100}%"></i>`:""}
        ${c.c?`<i class="c" style="width:${c.c/n*100}%"></i>`:""}
        ${c.p?`<i class="p" style="width:${c.p/n*100}%"></i>`:""}
      </span>
      <span class="num muted hidesm" style="font-size:11.5px;text-align:right;white-space:nowrap">${c.b} blancos</span>
      <span class="num muted hidesm" style="font-size:11.5px;text-align:right;white-space:nowrap">${eur(s.tic)}</span>
    </div>`).join("");
})();

/* ---------- reglas ---------- */
(function pintarReglas(){
  const head = `<thead><tr><th>Si la cuenta tiene</th><th>También tiende a tener</th>
    <th>Canasta</th><th class="n">Cuentas</th><th class="n">Confianza</th><th class="n">Lift</th></tr></thead>`;
  $("#reg-tbl").innerHTML = head + "<tbody>" + D.reglas.map(r=>`<tr>
      <td>${esc(r.a)}</td><td><b>${esc(r.b)}</b></td>
      <td class="muted">${r.canasta==="ejecutado"?"Ejecutados":"Ofrecidos"}</td>
      <td class="n">${r.n}</td><td class="n">${(r.conf*100).toFixed(0)}%</td>
      <td class="n"><b>${r.lift.toFixed(2)}×</b></td></tr>`).join("") + "</tbody>";
})();

/* ---------- metodo ---------- */
$("#method").innerHTML = [
  ["0.26","Afinidad","Market basket sobre las canastas de cada cuenta más el porcentaje de cuentas de la misma industria que ya ejecutan el servicio."],
  ["0.24","Demanda","Penetración del servicio en el portafolio Chile combinada con su win rate histórico."],
  ["0.20","Adyacencia","Cercanía al portafolio actual: 1.00 misma subfamilia, 0.75 misma familia, 0.50 mismo pilar, 0.10 cuenta sin nada ejecutado."],
  ["0.18","Valor","Ticket mediano histórico del servicio, normalizado en escala logarítmica."],
  ["0.12","Momentum","Pitches recientes del servicio y decaimiento exponencial desde su último movimiento."],
  ["×","Factores","Estado de la celda: 1.00 nunca ofrecido, 0.70 perdido, 0.55 en pausa. Una derrota de menos de 270 días castiga a 0.35."],
].map(([w,t,p])=>`<div><div class="w num">${w}</div><h3>${t}</h3><p>${p}</p></div>`).join("");

/* ---------- eventos ---------- */
$("#f-ind").addEventListener("change", pintarMatriz);
$("#f-fam").addEventListener("change", pintarMatriz);
document.querySelectorAll(".seg button").forEach(b=>b.addEventListener("click", ()=>{
  orden = b.dataset.sort;
  document.querySelectorAll(".seg button").forEach(x=>x.setAttribute("aria-pressed", String(x===b)));
  pintarMatriz();
}));
$("#matrix").addEventListener("click", ev=>{
  const t = ev.target.closest("[data-c]");
  if(!t) return;
  sel = +t.dataset.c; $("#f-cta").value = sel; pintarFicha(); marcarSeleccion();
  $("#ficha").scrollIntoView({behavior:"smooth", block:"start"});
});
$("#matrix").addEventListener("keydown", ev=>{
  if(ev.key==="Enter" || ev.key===" "){ const t = ev.target.closest(".mx-acct"); if(t){ ev.preventDefault(); t.click(); } }
});
$("#f-cta").addEventListener("change", e=>{ sel = +e.target.value; pintarFicha(); marcarSeleccion(); });
["#q","#f-prio","#f-tipo","#f-fam2"].forEach(s=>$(s).addEventListener("input", pintarOps));

pintarMatriz(); pintarFicha(); pintarOps();
</script>
"""
