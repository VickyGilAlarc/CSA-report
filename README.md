# Mapa de proyectos y oportunidades — CSA Chile

Mapa de lo que le vendimos a cada cliente, lo que está vivo y lo que nunca le
ofrecimos — con un filtro encima: **no todo hueco es una oportunidad**. Cuando
varias variantes resuelven lo mismo, el mapa propone una sola. Se construye desde
el export de pitches del CRM más el catálogo oficial de ZOHO, y produce un libro
Excel, un dashboard HTML y CSVs listos para minería.

```
python -m pip install -r requirements.txt
python run.py
```

| Salida | Para qué |
|---|---|
| `outputs/mapa_oportunidades_csa_cl.xlsx` | El entregable de trabajo: 16 hojas, matriz con colores y tablas listas para dinámicas |
| `outputs/mapa_csa_cl.html` | Dashboard navegable: mapa interactivo, ficha por cuenta, ranking filtrable |
| `outputs/csv/` | Base normalizada, celdas, oportunidades netas, grupos y perfiles para Looker / Power BI |

**Fuentes de datos** (ambas en `data/raw/`):

| Archivo | Rol |
|---|---|
| `Reporte_Pitches_CL.xlsx` | Historial de pitches del CRM: qué se ofreció, a quién y cómo terminó |
| `ZOHO_Catalogo_CSA_Latam.xlsx` | Catálogo oficial: define el universo de servicios, su jerarquía y sus precios de lista |

---

## 1. La lógica del mapa

### La celda es la unidad de análisis

El mapa **no** es la lista de pitches: es la grilla completa de **cuenta × servicio
del catálogo**. Con 29 cuentas y 106 servicios el mapa tiene **3.074 celdas**,
existan o no en el CRM. Esa es la decisión de diseño que hace posible ver los
espacios blancos: si solo miras lo que está registrado, lo que nunca ofreciste es
literalmente invisible.

El universo de columnas lo define el catálogo ZOHO, no el historial: entran los
servicios activos más cualquiera dado de baja que igual tenga pitches registrados
(de 118 filas del catálogo, 106 entran al mapa).

Cada celda recibe **un solo estado**, resolviendo por jerarquía cuando hay varios
pitches en el mismo cruce:

| Estado | Significado | Regla |
|---|---|---|
| `EJECUTADO` | Ya lo compra | Existe al menos un pitch en `6.Won` |
| `EN_CURSO` | Conversación viva | Hay `5.Pitching`, `2.Prospecting` o `1. Lead` |
| `EN_PAUSA` | Quedó frenado | Solo hay `8.On Hold` |
| `PERDIDO` | Se ofreció y no se ganó | Solo hay `10.Lost` |
| `BLANCO` | **Nunca ofrecido** | No hay ningún pitch en ese cruce |

Hoy: 22 ejecutadas, 24 en pipeline, 7 en pausa, 35 perdidas y **2.986 espacios
blancos** — 0,7% de cobertura del catálogo.

### Tres niveles de agregación

La jerarquía viene del propio catálogo ZOHO: `Pillar → Scope Of Service →
Business Category → Service`. Esto permite minar a cualquier altura: "¿qué cuentas
no tienen nada de Measurement & Attribution?" es una pregunta de scope, no de
servicio.

Las cuentas se clasifican por `industria`, `grupo_economico` y `tier`
(`config/cuentas.csv`), que es lo que habilita el benchmark entre comparables.

---

## 2. Oportunidad neta: el filtro de esfuerzo duplicado

Este es el problema que el mapa resuelve además del espacio blanco. Un cliente no
necesita las tres variantes de Online Data Optimization: con una basta. Proponer
las tres infla el pipeline con trabajo que en la práctica es el mismo.

Cada servicio pertenece a un **grupo de sustitución** con una de tres reglas
(`config/grupos_sustitucion.csv`):

| Regla | Qué significa | Ejemplos |
|---|---|---|
| `EXCLUSIVO` | Caminos alternativos al mismo resultado. Se elige uno. | las 3 ODO · las 4 rutas de CAPI · los enfoques de MMM · los 3 formatos de catálogo META |
| `ESCALABLE` | Escalones ordenados por `nivel`. Se entra por uno y se sube. | C-GenIA Basic/Intermediate/Advanced · ABCD Basic/Pro/Enterprise · DCO · contrato puntual vs anual |
| `ACUMULABLE` | Cosas distintas que sí suman. | modelos predictivos · ad hoc de distintas disciplinas · licencias |

Dentro de cada cuenta, el modelo asigna un **rol** a cada celda del grupo:

| Rol | Cuándo | ¿Cuenta como oportunidad? |
|---|---|---|
| `UNICO` | El servicio no tiene sustitutos | Sí |
| `REPRESENTANTE` | Grupo virgen: la variante de mejor score | Sí |
| `UPGRADE` | Hay algo implementado y este es el escalón siguiente | Sí, valorizado por la **diferencia** de precio |
| `ALTERNATIVA` | Otra variante del mismo caso ya contado | No — se guarda como opción de cotización |
| `CUBIERTO` | Un servicio hermano ya lo resuelve | No |

Reglas finas que hacen la diferencia:

- **Una propuesta viva bloquea a sus hermanos.** Si hay un pitch abierto en un
  grupo exclusivo o escalable, las demás variantes quedan cubiertas: no se
  pitchean dos versiones del mismo servicio en paralelo a la misma cuenta.
- **Se entra por el escalón mínimo.** En un grupo escalable sin nada implementado
  se propone la entrada, no toda la escalera.
- **Solo el siguiente escalón.** Con algo implementado se propone el upgrade
  inmediato, no todos los niveles superiores — y dentro de ese escalón también se
  elige una sola modalidad (mensual o anual, no ambas).

**Resultado sobre los datos actuales:**

| | |
|---|---|
| Universo bruto puntuable | 3.028 |
| **Oportunidades netas** | **2.043** |
| Alternativas descartadas | 918 |
| Celdas ya cubiertas | 67 |
| Duplicados evitados | **985 (33%)** |

La hoja `24_Grupos_Sustitucion` muestra la reducción grupo por grupo: ABCD Detector
−87%, C-GenIA −87%, CAPI −76%, MMM −78%, ODO −71%.

---

## 3. El score de oportunidad

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
| **Valor** | Ticket potencial | Valor anual de referencia, normalizado en log |
| **Momentum** | Si el servicio está vivo hoy | 0.5 × % de pitches recientes + 0.5 × decaimiento exponencial (semivida ≈ 8 meses) |
| **Adyacencia** | Cercanía al portafolio actual de la cuenta | 1.00 misma Business Category · 0.60 mismo Scope · 0.45 misma Capability · 0.35 mismo pilar · 0.20 cuenta activa cruzando de pilar · 0.10 cuenta sin nada ejecutado |

Los pesos de la adyacencia bajan rápido a propósito: `Tech Consulting` agrupa 60 de
los 106 servicios, así que compartir scope dice mucho menos que compartir categoría.

**De dónde sale el valor de referencia.** Manda el ticket mediano histórico de
Chile cuando existe (es lo que el mercado pagó de verdad); si no, el SRP de lista
del catálogo; y si el servicio es "a cotizar" sin historia, la mediana del
portafolio. La columna `fuente_valor` dice cuál se usó en cada caso. Los SRP
mensuales se anualizan ×12 para poder compararlos contra contratos anuales; los
valores históricos **no** se anualizan, porque ya son el monto cerrado del negocio.

**Factores multiplicativos**

- `factor_estado`: 1.00 nunca ofrecido · 0.70 perdido · 0.55 en pausa.
- `factor_recencia`: 0.35 si la derrota tiene menos de 270 días — re-pitchear algo
  que se perdió el mes pasado no es una oportunidad, es insistir.

**Prioridad** (umbrales absolutos, para comparar trimestre a trimestre):
`A ≥ 48` · `B ≥ 36` · `C` el resto · `-` para lo que no es oportunidad neta.
Hoy: 76 en A, 300 en B.

El score se calcula en dos pasadas: la primera con el precio completo del servicio,
luego se asignan los roles de grupo, y la segunda recalcula el eje de valor de los
upgrades sobre su delta en vez del precio de lista.

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

## 4. Cómo usarlo para minar una cuenta

En el **Excel**:

- `10_Mapa_Cobertura` — la matriz completa. Filtra una fila y lee los huecos.
- `11_Mapa_Familias` — % de cobertura por scope: dónde la cuenta está entera en cero.
- `20_Oportunidades_Netas` — el ranking limpio, sin duplicados.
- `21_Top_por_Cuenta` — las 5 mejores jugadas de cada cuenta con su motivo.
- `22_Reactivacion` — perdidos maduros, propuestas en pausa y upgrades.
- `23_Alternativas_Descartadas` — lo que el modelo sacó y por qué. Es la hoja para
  discutir la variante concreta a cotizar con el cliente.
- `24_Grupos_Sustitucion` — cuánto duplicado evita cada grupo.
- `40_Afinidad_Servicios` — "quien tiene A también tiene B", para armar el pitch.
- `91_Celdas_Cuenta_Servicio` — el grano fino: una fila por cruce, para dinámicas.

En el **dashboard**: clic en cualquier celda o nombre de cuenta abre su ficha con
portafolio, cobertura por familia y jugadas priorizadas.

Preguntas que el modelo responde directo:

- ¿Qué scopes completos no le hemos tocado a esta cuenta? → `11_Mapa_Familias`
- ¿Qué compran sus comparables de industria que ella no? → columna `adopcion_industria_pct`
- ¿Qué servicio tiene más mercado sin tocar? → `cuentas_blanco` en `31_Perfil_Servicios`
- ¿Qué perdimos hace suficiente tiempo como para volver? → `22_Reactivacion`
- ¿Cuál de las tres ODO le corresponde a esta cuenta? → `23_Alternativas_Descartadas`
  filtrando por cuenta y grupo `ODO`: están las tres con su score
- ¿Dónde estoy proponiendo trabajo que ya está hecho? → rol `CUBIERTO`

---

## 5. Actualizar con datos nuevos

1. Reemplazar `data/raw/Reporte_Pitches_CL.xlsx` y/o
   `data/raw/ZOHO_Catalogo_CSA_Latam.xlsx` por el export nuevo.
2. `python run.py`.

El pipeline **se detiene con un error explícito** si aparece un servicio, una
cuenta o una fase que no está clasificada. Es deliberado: obliga a clasificar lo
nuevo en `config/` y evita que el mapa se degrade en silencio con el tiempo.

### Qué se puede ajustar sin tocar código

| Archivo | Qué controla |
|---|---|
| `config/parametros.yaml` | Pesos del score, umbrales A/B, mapeo de fases, plazo de reactivación, ventana de momentum, comportamiento de la sustitución |
| `config/servicios_reglas.csv` | Etiqueta corta, grupo de sustitución, nivel y modalidad de cada servicio del catálogo |
| `config/grupos_sustitucion.csv` | La regla de cada grupo (`EXCLUSIVO` / `ESCALABLE` / `ACUMULABLE`) y por qué existe |
| `config/cuentas.csv` | Industria, grupo económico y tier de cada cuenta |

Lo que **no** se edita a mano: la jerarquía y los precios de los servicios. Eso
viene del catálogo ZOHO y se actualiza reemplazando el archivo.

**Si el criterio de sustitución cambia** — por ejemplo, si se decide que un cliente
sí puede tener DCO Basic y Advanced a la vez — se edita la regla de ese grupo en
`grupos_sustitucion.csv` y el mapa completo se recalcula. No hay que tocar código.

---

## 6. Estructura

```
config/          reglas de sustitución, ficha de cuentas y parámetros del modelo
data/raw/        export del CRM y catálogo ZOHO, sin tocar
src/csa_map/
  config.py        carga y valida la configuración
  catalog.py       lee el catálogo ZOHO y le adosa las reglas de sustitución
  ingest.py        normaliza el export del CRM y lo enriquece con el catálogo
  coverage.py      matriz cuenta × servicio, valor de referencia y perfiles
  affinity.py      market basket y adopción por industria
  scoring.py       score de oportunidad, prioridad, motivo y acción
  substitution.py  roles de grupo: separa oportunidad neta de esfuerzo duplicado
  pipeline.py      orquestador
  excel_report.py / dashboard.py   entregables
run.py           construye todo
```

---

## Notas sobre los datos de origen

- Los montos de `PROJECT PRICE (Lcy)` vienen **en EUR** (CLP ya convertido por la
  tasa de cambio de la fila). Todo el mapa está en EUR.
- La columna `Canal` tiene un único valor (`Standard`) en las 114 filas: no aporta
  y no se usa.
- Un registro trae `BI Services` marcado como `CSA - Science` cuando el catálogo lo
  tiene como `CSA - Tech`. Manda el catálogo; la discrepancia queda marcada en la
  columna `discrepancia_pilar` de `90_Base_Normalizada`.
- Los 30 servicios pitcheados existen textualmente en el catálogo ZOHO: el empalme
  es exacto, sin cruce difuso de nombres.
- El catálogo trae 13 servicios `Inactive`. Se excluyen del mapa salvo que tengan
  historial de pitch (es el caso de `C-GenIA`). Por eso tres grupos de sustitución
  aparecen con 0% de reducción: su segunda variante está dada de baja.
- **`TUA` quedó sin industria** (`Por clasificar`) en `config/cuentas.csv`. Es la
  única cuenta sin clasificar y conviene completarla: sin industria no recibe señal
  de comparables y su afinidad se calcula solo con el promedio de mercado.
