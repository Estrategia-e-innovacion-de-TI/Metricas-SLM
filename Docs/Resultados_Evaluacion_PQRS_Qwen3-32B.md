# Resultados de evaluación de Qwen3-32B para PQRS

Documento de resultados medidos. No contiene prompts, payloads, textos de solicitudes, respuestas crudas ni identificadores de casos.

## 1. Alcance

- Caso de uso: clasificación de solicitudes PQRS.
- Modelo: `qwen.qwen3-32b-v1:0`.
- Clases: `Queja`, `Petición` y `Reclamo`.
- Dataset de las corridas completas: 100 registros anonimizados.
- Referencias humanas: conservadas localmente y fuera del payload.
- Temperatura: `0`.
- Corridas completas: streaming, `max_tokens=384`, `response_format=json_object` habilitado en el gateway.

Las métricas de clasificación se reportan en dos formas cuando aplica:

- **Estricto:** usa la respuesta sin retirar ningún envoltorio de formato.
- **Recuperable:** retira únicamente el envoltorio Markdown de JSON y vuelve a calcular la clasificación. No modifica el contenido del JSON ni corrige predicciones.

## 2. Resumen ejecutivo

| Indicador | Línea base recuperable | Prompt con ejemplos | Variación |
|---|---:|---:|---:|
| Accuracy | 81,00 % | 85,00 % | +4,00 pp |
| Macro-F1 | 52,49 % | 76,60 % | +24,10 pp |
| Recall de Queja | 0,00 % | 50,00 % | +50,00 pp |
| F1 de Queja | 0,00 % | 66,67 % | +66,67 pp |
| Casos correctos | 81/100 | 85/100 | +4 casos |
| HTTP 200 | 100/100 | 100/100 | Sin cambio |

Los ejemplos contrastivos mejoraron la clasificación, principalmente en `Queja`. La muestra de esa clase contiene solo 4 casos, por lo que el resultado debe confirmarse con más casos.

## 3. Corrida piloto: 4 casos

Esta fue una prueba técnica inicial y no constituye la línea base definitiva.

| Indicador | Resultado |
|---|---:|
| Casos procesados | 4 |
| HTTP 200 | 4/4 (100 %) |
| JSON aceptado sin recuperación | 2/4 (50 %) |
| Latencia media | 1.462,001 ms |
| Latencia P50 | 1.321,276 ms |
| Latencia P95 | 2.353,244 ms |
| TTFT medio | 842,263 ms |
| TTFT P50 | 862,255 ms |
| TTFT P95 | 965,067 ms |
| Costo reportado | USD 0,00114090 |

Hallazgo técnico: hubo respuestas envueltas en Markdown y un caso truncado por el límite de salida.

## 4. Línea base: corrida PQRS-003

### 4.1 Clasificación

| Indicador | Estricto | Recuperable |
|---|---:|---:|
| Accuracy | 1,00 % | 81,00 % |
| Casos correctos | 1/100 | 81/100 |
| Macro-F1 | 0,995 % | 52,49 % |
| Predicciones válidas | 1/100 | 100/100 |
| Predicciones inválidas | 99/100 | 0/100 |

### 4.2 Métricas por clase — clasificación recuperable

| Clase | Soporte | Verdaderos positivos | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|
| Queja | 4 | 0 | 0,00 % | 0,00 % | 0,00 % |
| Petición | 30 | 18 | 85,71 % | 60,00 % | 70,59 % |
| Reclamo | 66 | 63 | 79,75 % | 95,45 % | 86,90 % |

### 4.3 Matriz de confusión — clasificación recuperable

Filas: clase real. Columnas: clase predicha.

| Real \ Predicha | Queja | Petición | Reclamo | Inválida |
|---|---:|---:|---:|---:|
| Queja | 0 | 0 | 4 | 0 |
| Petición | 0 | 18 | 12 | 0 |
| Reclamo | 0 | 3 | 63 | 0 |
| Inválida | 0 | 0 | 0 | 0 |

### 4.4 Rendimiento y operación

| Indicador | Resultado |
|---|---:|
| Casos procesados | 100 |
| HTTP 200 | 100/100 |
| Latencia media | 1.556,853 ms |
| Latencia P50 | 1.303,161 ms |
| Latencia P95 | 2.471,165 ms |
| TTFT medio | 1.046,990 ms |
| TTFT P50 | 818,933 ms |
| TTFT P95 | 1.890,308 ms |
| Tokens de entrada | 213.756 |
| Tokens de salida | 9.053 |
| Costo total reportado | USD 0,03749520 |
| Registros con usage | 100/100 |

### 4.5 Formato de salida

| Indicador | Resultado |
|---|---:|
| JSON estricto aceptado sin limpieza | 1/100 |
| Respuestas con envoltorio Markdown | 99/100 |
| Respuestas recuperadas retirando solo el envoltorio | 99/100 |
| No recuperables | 1/100 |

`response_format=json_object` fue aceptado por el gateway, pero no garantizó JSON estricto en la respuesta del modelo.

## 5. Corrida con ejemplos sintéticos: PQRS-004

Los ejemplos sintéticos se incluyeron únicamente como guía dentro del prompt. No se agregaron como registros de evaluación.

### 5.1 Clasificación

| Indicador | Estricto | Recuperable |
|---|---:|---:|
| Accuracy | 0,00 % | 85,00 % |
| Casos correctos | 0/100 | 85/100 |
| Macro-F1 | 0,00 % | 76,60 % |
| Predicciones válidas | 0/100 | 100/100 |
| Predicciones inválidas | 100/100 | 0/100 |

### 5.2 Métricas por clase — clasificación recuperable

| Clase | Soporte | Verdaderos positivos | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|
| Queja | 4 | 2 | 100,00 % | 50,00 % | 66,67 % |
| Petición | 30 | 18 | 94,74 % | 60,00 % | 73,47 % |
| Reclamo | 66 | 65 | 82,28 % | 98,48 % | 89,66 % |

### 5.3 Matriz de confusión — clasificación recuperable

Filas: clase real. Columnas: clase predicha.

| Real \ Predicha | Queja | Petición | Reclamo | Inválida |
|---|---:|---:|---:|---:|
| Queja | 2 | 0 | 2 | 0 |
| Petición | 0 | 18 | 12 | 0 |
| Reclamo | 0 | 1 | 65 | 0 |
| Inválida | 0 | 0 | 0 | 0 |

### 5.4 Rendimiento y operación

| Indicador | Resultado |
|---|---:|
| Casos procesados | 100 |
| HTTP 200 | 100/100 |
| Latencia media | 1.368,998 ms |
| Latencia P50 | 1.228,829 ms |
| Latencia P95 | 2.223,441 ms |
| TTFT medio | 912,067 ms |
| TTFT P50 | 825,634 ms |
| TTFT P95 | 1.196,630 ms |
| Tokens de entrada | 234.256 |
| Tokens de salida | 8.640 |
| Costo total reportado | USD 0,04032240 |
| Registros con usage | 100/100 |

### 5.5 Formato de salida

| Indicador | Resultado |
|---|---:|
| JSON estricto aceptado sin limpieza | 0/100 |
| Respuestas con envoltorio Markdown | 100/100 |
| Respuestas recuperadas retirando solo el envoltorio | 100/100 |
| No recuperables | 0/100 |

## 6. Lectura de la matriz de confusión

### Línea base recuperable

- Las 4 solicitudes reales de `Queja` fueron clasificadas como `Reclamo`.
- 12 de 30 solicitudes reales de `Petición` fueron clasificadas como `Reclamo`.
- 3 solicitudes reales de `Reclamo` fueron clasificadas como `Petición`.
- El principal patrón de error fue la sobrerrepresentación de `Reclamo`.

### Prompt con ejemplos

- 2 de 4 solicitudes reales de `Queja` fueron clasificadas correctamente.
- 12 de 30 solicitudes reales de `Petición` continuaron clasificándose como `Reclamo`.
- 65 de 66 solicitudes reales de `Reclamo` fueron clasificadas correctamente.
- La confusión entre `Petición` y `Reclamo` persiste.

## 7. Limitaciones de interpretación

- El resultado de `Queja` tiene soporte de solo 4 casos.
- La métrica recuperable no debe confundirse con cumplimiento estricto del formato.
- Las respuestas crudas y los datos de entrada permanecen fuera del repositorio.
- Estos resultados miden clasificación y desempeño técnico; no constituyen una evaluación completa de calidad del resumen, seguridad, costos operativos bajo carga ni aptitud para producción.
- La comparación debe conservar el mismo dataset, referencias, configuración y método de cálculo.

## 8. Fuentes locales de trazabilidad

Los cálculos provienen de los siguientes archivos locales, excluidos del repositorio:

- `metricas/pqrs_classification_metrics.json`
- `metricas/prompt_examples/pqrs_classification_metrics.json`
- `resultados/pqrs_gateway_results.jsonl`
- `resultados/pqrs_gateway_results_prompt_examples.jsonl`

La metodología y el registro consolidado de las corridas están documentados en:

`Docs/Linea_Base_Tecnica_Evaluacion_Qwen_32B_Casos_Bancarios_CONSOLIDADO.docx`
