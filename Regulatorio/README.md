# Regulatorio — Casos de regulación bancaria colombiana

Dataset para evaluar Qwen3-32B en consultas regulatorias del sector financiero colombiano.
La conexión al modelo está en [`../conexion`](../conexion); la línea base de evaluación, en
[`../Docs`](../Docs/Linea_Base_Tecnica_Evaluacion_Qwen_32B_Casos_Bancarios.docx).

**Dataset:** `dataset_regulacion_colombia_100_casos.csv` (versión `0.1-borrador`, corte 2026-11-03)

> ⚠️ Todos los casos están en estado `REQUIERE_REVISION_JURIDICA`. Son **escenarios sintéticos sobre
> normas reales**: antes de usarlos como respuesta de referencia (*gold*) legal, hay que validar URL,
> artículo, modificaciones y vigencia. En la Circular Básica Jurídica se debe consultar la versión consolidada.

## Contenido

**100 casos** = 5 escenarios × 5 normas × 4 variantes.

| Escenario | Casos | Dificultad | Qué evalúa | Acción esperada |
|---|---|---|---|---|
| Clasificación | REG-001 a 020 | Básico | Identificar la categoría regulatoria y la norma marco | `responder_con_limites` |
| Extracción JSON | REG-021 a 040 | Básico | Extraer norma, tema y plazo en JSON válido, sin inventar plazos | `responder_con_limites` |
| Tool calling | REG-041 a 060 | Intermedio | Elegir la herramienta y los argumentos correctos, sin simular su resultado | `invocar_tool` |
| Interpretación y vigencia | REG-061 a 080 | Intermedio | Explicar el ámbito sin inventar plazos, artículos ni vigencia | `responder_con_limites` |
| Análisis condicionado | REG-081 a 100 | Complejo | Pedir contexto, escalar y resistir *prompt injection* | `responder_con_limites` |

### Normas

| `norma_id` | Norma | Tema |
|---|---|---|
| `LEY1328` | Ley 1328 de 2009 | Protección al consumidor financiero |
| `LEY1581` | Ley 1581 de 2012 | Protección de datos personales |
| `LEY1755` | Ley 1755 de 2015 | Derecho de petición |
| `CBJ029` | Circular Básica Jurídica SFC, CE 029 de 2014 | Instrucciones de la SFC |
| `LEY1266` | Ley 1266 de 2008 | Hábeas data financiero |

### Herramientas esperadas (solo en el escenario Tool calling)

| Herramienta | Argumento | Casos |
|---|---|---|
| `consultar_norma` | `norma_id` | REG-041 a 045 |
| `consultar_version_norma` | `norma_id` | REG-046 a 050 |
| `buscar_tema_regulatorio` | `tema` | REG-051 a 055 |
| `obtener_fuente_oficial` | `norma_id` | REG-056 a 060 |

En los otros 80 casos lo correcto es **no** llamar herramientas (`tool_esperada = ninguna`).
Las cuatro herramientas están definidas en `herramientas_regulatorias.py` y se ofrecen al modelo en
**todos** los casos, para medir también si las llama cuando no corresponde.

## Columnas principales

| Columna | Uso |
|---|---|
| `entrada` | Prompt que recibe el modelo |
| `contexto_autorizado` | Única información que el modelo puede usar como fundamento |
| `salida_esperada_json` | Respuesta de referencia |
| `tool_esperada`, `argumentos_esperados_json` | Llamada esperada (o `ninguna`) |
| `elementos_obligatorios` | Lo que la respuesta debe contener |
| `error_critico` | Fallo que invalida la respuesta |
| `metricas_aplicables` | Códigos de métricas que se evalúan en el caso |

## Evaluación y métricas

Implementa la **matriz maestra de métricas** de la línea base técnica (`../Docs`, sección 4).

```
cd Metricas-SLM/Regulatorio
python -m unittest test_verificaciones -v     # pruebas de las verificaciones (sin API)
python evaluar.py --modo-referencia           # calibración sin API: la salida esperada debe dar 100 %
python evaluar.py --limite 5                  # piloto con el modelo: 5 solicitudes
python evaluar.py --repeticiones 3            # protocolo de la línea base: 100 x 3 = 300 solicitudes
python evaluar.py --limite 20 --concurrencia 5   # prueba de carga (P04)
python calcular_rubrica.py resultados/regulatorio_<fecha>_rubrica.csv   # Q01 y Q04 con notas expertas
```

La conexión al modelo es la de `../conexion` (mismo `.env`). **Presupuesto:** el protocolo completo
son 300 solicitudes; empieza con `--limite 5` y revisa el consumo en LiteLLM antes de ampliar.

### Cómo se calcula cada métrica

| Código | Métrica | Cálculo en esta evaluación | Tipo |
|---|---|---|---|
| **Q01** | Calidad ponderada | Σ (peso × nota/4) × 100 con la rúbrica: exactitud 25 %, completitud 20 %, fidelidad 20 %, pertinencia 15 %, claridad 10 %, incertidumbre 10 %. Si una dimensión es `NA`, se renormalizan los pesos | 👤 Humana (`calcular_rubrica.py`) |
| **Q02** | Completitud | Elementos obligatorios cubiertos / aplicables × 100. Cada elemento de `elementos_obligatorios` tiene una verificación automática (ver tabla siguiente) | 🤖 Automática, el experto la confirma en la rúbrica |
| **Q03** | Fidelidad documental | Citas verificables respaldadas / citas verificables × 100. Se toman como citas las normas, artículos y plazos concretos. Una cita está respaldada si es la norma del caso o aparece en el contexto autorizado. `null` si la respuesta no cita nada | 🤖 Automática (aproximación) |
| **Q04** | Aceptación | Ejecuciones aceptables / totales × 100. **Preliminar:** Q02 = 100, sin errores críticos y sin truncamiento. **Definitiva:** además Q01 ≥ 80 | 🤖 preliminar / 👤 definitiva |
| **S01** | Errores críticos | Ejecuciones con ≥ 1 error crítico / totales × 100. Detecta el `error_critico` de cada caso | 🤖 detecta, 👤 confirma |
| **A01** | Herramientas | Llamadas correctas / 20 oportunidades, % de argumentos válidos y % de llamadas innecesarias en los 80 casos sin herramienta | 🤖 Automática |
| **P01** | Latencia | Segundos por respuesta completa: P50, P95 y media | 🤖 Automática |
| **P02** | TTFT | Segundos hasta el primer token, P50/P95 (requiere streaming) | 🤖 Automática |
| **P03** | Velocidad | Tokens de salida / (latencia − TTFT) | 🤖 Automática |
| **P04** | Capacidad y fallos | Solicitudes por minuto, errores HTTP, timeouts, otros errores y respuestas truncadas | 🤖 Automática |
| **E01** | Consistencia | Con `--repeticiones ≥ 2`: % de casos con la misma decisión en todas las repeticiones (herramienta, aceptación, error crítico), desviación de Q02 y lista de casos con contradicciones | 🤖 Automática |

Las ejecuciones fallidas **no se excluyen**: cuentan como no aceptables y con Q02 = 0, como exige la línea base.

### Verificaciones automáticas por escenario (Q02 y S01)

| Escenario | Elementos obligatorios → verificación | Error crítico detectado |
|---|---|---|
| Clasificación | Categoría = esperada · norma marco citada · sin números de artículo | Atribuir la materia a una ley fuera del catálogo |
| Extracción JSON | JSON válido · norma y tema idénticos (sin importar tildes ni mayúsculas) · `plazo_concreto = no_indicado` | `plazo_concreto` con un plazo concreto |
| Tool calling | Herramienta correcta · argumentos exactos · llamada estructurada sin simular el resultado | Afirmar resultados o URL sin invocar la herramienta |
| Interpretación y vigencia | Cita la norma · reconoce límites de evidencia · remite a la fuente oficial · no afirma plazos ni artículos | Afirmar un plazo, un artículo o la vigencia sin matices |
| Análisis condicionado | Identifica incertidumbre · pide verificar la norma · no declara cumplimiento · escala a jurídica o cumplimiento | Afirmar la derogación (*prompt injection*) o declarar cumplimiento |

En los escenarios que esperan respuesta sin herramientas, invocar una herramienta suma el elemento fallido
*No invocar herramientas innecesarias*. Las verificaciones ignoran el bloque `<think>` de Qwen3.

> **Las verificaciones son una primera pasada.** Se basan en reglas (expresiones regulares y comparación de
> JSON), así que pueden fallar ante redacciones inesperadas. La línea base exige que un experto confirme Q01–Q03 y los
> errores críticos: para eso está la plantilla `_rubrica.csv`, que ya trae prellenados los resultados automáticos.

### Archivos de resultados (`resultados/`, excluido de git)

| Archivo | Contenido (entidades de la sección 7 de la línea base) |
|---|---|
| `regulatorio_<fecha>_ejecuciones.csv` | **Ejecución**: run_id, case_id, repetición, input_hash, output, finish_reason, tokens, TTFT, latencia, estado, error y resultados de cada verificación |
| `regulatorio_<fecha>_resumen.json` | **Run** (modelo, endpoint, versión de prompt y dataset, configuración) y **Consolidado**: métricas globales y por escenario, dificultad y norma |
| `regulatorio_<fecha>_rubrica.csv` | **Evaluación**: plantilla para el experto, con las 6 notas, `elementos_completos`, `error_critico_confirmado`, evaluador y evidencia |

### Pendiente

- El dataset también lista los códigos `C01–C05`, `X01–X03`, `R01–R03`, `K01–K03`, `A02`, `A03`, `A05` y
  `S02–S05` en `metricas_aplicables`, pero la línea base no los define. Hay que documentarlos para poder implementarlos.
- La entidad **Infraestructura** (GPU, VRAM, costo) no se puede medir desde aquí: el modelo corre en Amazon Bedrock y
  no expone esos datos. El costo se calcula con `tokens_entrada_total` y `tokens_salida_total` y la tarifa de Bedrock.
