# Mapa de proyectos y oportunidades — CSA Chile

Mapa de lo que le vendimos a cada cliente, lo que está vivo y —sobre todo— lo que
nunca le ofrecimos. Se construye desde el export de pitches del CRM y produce un
libro Excel, un dashboard HTML y CSVs listos para minería.

```
python -m pip install -r requirements.txt
python run.py
```

| Salida | Para qué |
|---|---|
| `outputs/mapa_oportunidades_csa_cl.xlsx` | El entregable de trabajo: 14 hojas, matriz con colores y tablas listas para dinámicas |
| `outputs/mapa_csa_cl.html` | Dashboard navegable: mapa interactivo, ficha por cuenta, ranking filtrable |
| `outputs/csv/` | Base normalizada, celdas, oportunidades y perfiles para conectar a Looker / Power BI |

---

## 1. La lógica del mapa

### La celda es la unidad de análisis

El mapa **no** es la lista de pitches: es la grilla completa de **cuenta × servicio
del catálogo**. Con 29 cuentas y 30 servicios el mapa tiene **870 celdas**, existan
o no en el CRM. Esa es la decisión de diseño que hace posible ver los espacios
blancos: si solo miras lo que está registrado, lo que nunca ofreciste es
literalmente invisible.

Cada celda recibe **un solo estado**, resolviendo por jerarquía cuando hay varios
pitches en el mismo cruce:

| Estado | Significado | Regla |
|---|---|---|
| `EJECUTADO` | Ya lo compra | Existe al menos un pitch en `6.Won` |
| `EN_CURSO` | Conversación viva | Hay `5.Pitching`, `2.Prospecting` o `1. Lead` |
| `EN_PAUSA` | Quedó frenado | Solo hay `8.On Hold` |
| `PERDIDO` | Se ofreció y no se ganó | Solo hay `10.Lost` |
| `BLANCO` | **Nunca ofrecido** | No hay ningún pitch en ese cruce |

Hoy: 22 ejecutadas, 24 en pipeline, 7 en pausa, 35 perdidas y **782 espacios
blancos** — 2,5% de cobertura del catálogo.

### Tres niveles de agregación

Todo servicio se clasifica en `pilar → familia → subfamilia`
(`config/taxonomia_servicios.csv`). Esto permite minar a cualquier altura:
"¿qué cuentas no tienen nada de Measurement?" es una pregunta de familia, no de
servicio, y sin la taxonomía no se puede responder.

Las cuentas se clasifican por `industria`, `grupo_economico` y `tier`
(`config/cuentas.csv`), que es lo que habilita el benchmark entre comparables.

---

## 2. El score de oportunidad

Cada celda que **no** está ejecutada ni en conversación recibe un score 0–100:

```
score = 100 × ( 0.24·demanda + 0.26·afinidad + 0.18·valor
              + 0.12·momentum + 0.20·adyacencia )
        × factor_estado × factor_recencia
```

| Componente | Qué mide | Cómo se calcula |
|---|---|---|
| **Demanda** | Qué tan vendible es el servicio en Chile | 0.6 × penetración normalizada + 0.4 × win rate del servicio |
| **Afinidad** | Que cuentas parecidas ya lo compran | 0.55 × market basket + 0.45 × adopción en la misma industria |
| **Valor** | Ticket potencial | Ticket mediano histórico, normalizado en log |
| **Momentum** | Si el servicio está vivo hoy | 0.5 × % de pitches recientes + 0.5 × decaimiento exponencial (semivida ≈ 8 meses) |
| **Adyacencia** | Cercanía al portafolio actual de la cuenta | 1.00 misma subfamilia · 0.75 misma familia · 0.50 mismo pilar · 0.25 cuenta activa cruzando de pilar · 0.10 cuenta sin nada ejecutado |

**Factores multiplicativos**

- `factor_estado`: 1.00 nunca ofrecido · 0.70 perdido · 0.55 en pausa.
- `factor_recencia`: 0.35 si la derrota tiene menos de 270 días — re-pitchear algo
  que se perdió el mes pasado no es una oportunidad, es insistir.

**Prioridad** (umbrales absolutos, para comparar trimestre a trimestre):
`A ≥ 48` · `B ≥ 36` · `C` el resto. Hoy: 32 en A, 189 en B.

Cada oportunidad trae además un `motivo` en texto plano (por qué subió) y una
`accion_sugerida` (upsell, cross-sell, abrepuertas, destrabar, re-pitchear).

### La afinidad en detalle

Es la señal que hace el trabajo de minería, y son dos cosas distintas:

1. **Market basket.** Para cada par de servicios (A → B) se calculan soporte,
   confianza y **lift** sobre las canastas de cada cuenta. Se arman dos canastas:
   la de servicios *ejecutados* (señal fuerte de compra) y la de *ofrecidos*
   (señal de cómo se arma comercialmente la conversación). La confianza usa
   suavizado de Laplace para que "1 de 1 caso" no pese como "5 de 5".
2. **Adopción por industria.** Qué porcentaje de las cuentas de la misma industria
   ya ejecuta el servicio. Cuando la industria tiene menos de 2 cuentas
   comparables no informa nada y se cae al promedio de mercado.

Con el volumen actual (22 celdas ejecutadas) el market basket es todavía una señal
débil y el peso lo carga la adopción por industria. A medida que entren más
ejecuciones la primera señal gana fuerza sola, sin tocar el código.

---

## 3. Cómo usarlo para minar una cuenta

En el **Excel**:

- `10_Mapa_Cobertura` — la matriz completa. Filtra una fila y lee los huecos.
- `11_Mapa_Familias` — % de cobertura por familia: dónde la cuenta está entera en cero.
- `21_Top_por_Cuenta` — las 5 mejores jugadas de cada cuenta con su motivo.
- `22_Reactivacion` — perdidos maduros y propuestas en pausa por destrabar.
- `40_Afinidad_Servicios` — "quien tiene A también tiene B", para armar el pitch.
- `91_Celdas_Cuenta_Servicio` — el grano fino: una fila por cruce, para dinámicas.

En el **dashboard**: clic en cualquier celda o nombre de cuenta abre su ficha con
portafolio, cobertura por familia y jugadas priorizadas.

Preguntas que el modelo responde directo:

- ¿Qué familias completas no le hemos tocado a esta cuenta? → `11_Mapa_Familias`
- ¿Qué compran sus comparables de industria que ella no? → columna `adopcion_industria_pct`
- ¿Qué servicio tiene más mercado sin tocar? → `cuentas_blanco` en `31_Perfil_Servicios`
- ¿Qué perdimos hace suficiente tiempo como para volver? → `22_Reactivacion`

---

## 4. Actualizar con datos nuevos

1. Reemplazar `data/raw/Reporte_Pitches_CL.xlsx` por el export nuevo.
2. `python run.py`.

El pipeline **se detiene con un error explícito** si aparece un servicio, una
cuenta o una fase que no está clasificada. Es deliberado: obliga a clasificar lo
nuevo en `config/` y evita que el mapa se degrade en silencio con el tiempo.

### Qué se puede ajustar sin tocar código

| Archivo | Qué controla |
|---|---|
| `config/parametros.yaml` | Pesos del score, umbrales A/B, mapeo de fases, plazo de reactivación, ventana de momentum |
| `config/taxonomia_servicios.csv` | Familia, subfamilia, pilar, modelo comercial y etiqueta corta de cada servicio |
| `config/cuentas.csv` | Industria, grupo económico y tier de cada cuenta |

Para **servicios del catálogo que nunca se le han ofrecido a nadie**: agregarlos a
la taxonomía con `en_catalogo=SI`. Entran al mapa como columna nueva, en blanco
para todas las cuentas, y compiten en el score con los demás.

---

## 5. Estructura

```
config/          taxonomía de servicios, ficha de cuentas y parámetros del modelo
data/raw/        export del CRM sin tocar
src/csa_map/
  config.py      carga y valida la configuración
  ingest.py      normaliza el export y lo enriquece con la taxonomía
  coverage.py    matriz cuenta × servicio, perfil de cuentas y de servicios
  affinity.py    market basket y adopción por industria
  scoring.py     score de oportunidad, prioridad, motivo y acción
  pipeline.py    orquestador
  excel_report.py / dashboard.py   entregables
run.py           construye todo
```

---

## Notas sobre los datos de origen

- Los montos de `PROJECT PRICE (Lcy)` vienen **en EUR** (CLP ya convertido por la
  tasa de cambio de la fila). Todo el mapa está en EUR.
- La columna `Canal` tiene un único valor (`Standard`) en las 114 filas: no aporta
  y no se usa.
- Un registro trae `BI Services` marcado como `CSA - Science` cuando el resto lo
  tiene como `CSA - Tech`. Manda la taxonomía; la discrepancia queda marcada en la
  columna `discrepancia_pilar` de `90_Base_Normalizada`.
- **`TUA` quedó sin industria** (`Por clasificar`) en `config/cuentas.csv`. Es la
  única cuenta sin clasificar y conviene completarla: sin industria no recibe señal
  de comparables y su afinidad se calcula solo con el promedio de mercado.
