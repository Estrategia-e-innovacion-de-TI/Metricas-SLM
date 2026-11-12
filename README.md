# Evaluación de Qwen3-32B para PQRS

Este repositorio contiene el código y la documentación de una evaluación de Qwen3-32B aplicada a clasificación de solicitudes PQRS.

La evaluación usa un gateway compatible con la API de OpenAI. El modelo recibe la descripción anonimizada de cada solicitud y debe responder un objeto con:

- `classification`: `Queja`, `Petición` o `Reclamo`.
- `summary`: resumen breve y fiel de la solicitud.

Los datos de entrada, las respuestas crudas y las métricas generadas se mantienen fuera del repositorio porque pueden contener información de evaluación o texto derivado de los casos.

## Contenido

```text
code/
  evaluar_pqrs.py              Ejecución de casos PQRS contra el gateway.
  gateway_model_test.py        Prueba mínima de conectividad y payload.
  calcular_metricas_pqrs.py    Métricas locales de clasificación.
  generar_reporte_html_pqrs.py Reporte HTML local a partir de métricas.
  anonimizar_columna.py         Utilidad local de anonimización.
  .env.example                  Plantilla de configuración sin secretos.
Docs/
  Linea_Base_Tecnica_Evaluacion_Qwen_32B_Casos_Bancarios_CONSOLIDADO.docx

Directorios locales no publicados:
  data/                          Dataset y referencias de evaluación.
  resultados/                    Respuestas crudas del gateway.
  metricas/                      Métricas, CSV, Excel y reportes generados.
  fraude/                        Investigación separada.
```

## Requisitos

- Python 3.11 o posterior.
- Acceso autorizado al gateway compatible con OpenAI.
- `openpyxl` para calcular métricas desde el XLSX local.

Instalación de la dependencia usada por el cálculo local:

```bash
python -m pip install openpyxl
```

No se requiere instalar una biblioteca HTTP adicional: la ejecución usa la biblioteca estándar de Python.

## Configuración

Copiar la plantilla y completar los valores únicamente en la copia local:

```bash
cd code
cp .env.example .env
```

En Windows Git Bash también puede usarse:

```bash
cp code/.env.example code/.env
```

Variables:

| Variable | Obligatoria | Uso |
|---|---:|---|
| `GATEWAY_URL` | Sí | URL del endpoint de completions del gateway. |
| `GATEWAY_API_KEY` | No | Token de autenticación. Se envía en el encabezado `Authorization`; no se registra en resultados. |
| `MODEL_NAME` | Sí | Identificador del modelo configurado en el gateway. |
| `GATEWAY_TIMEOUT` | No | Timeout en segundos. Por defecto: `60`. |
| `VERIFY_TLS` | No | Verificación TLS. Por defecto: `true`. No desactivarla en una conexión productiva. |
| `USE_RESPONSE_FORMAT` | No | Envía `response_format={"type":"json_object"}` cuando vale `true`. Por defecto: `false`. |
| `TEST_PROMPT` | No | Texto usado por la prueba de conectividad. |

El archivo `code/.env` está excluido por `.gitignore`. No subir tokens, URLs con credenciales ni certificados privados.

## Dónde están el prompt y el payload

### Evaluación PQRS: `code/evaluar_pqrs.py`

El prompt se construye en `build_messages(description)`:

1. Un mensaje `system` con las definiciones operativas de `Petición`, `Reclamo` y `Queja`.
2. Reglas para clasificar por la intención y el problema principal, no por palabras clave.
3. Ejemplos sintéticos contrastivos de las tres clases.
4. Instrucción de responder solo un objeto JSON con las claves `classification` y `summary`.
5. Un mensaje `user` con la descripción anonimizada del caso.

El payload se construye en `build_payload(messages, stream)` y tiene esta estructura lógica:

```json
{
  "model": "<MODEL_NAME>",
  "messages": [
    {"role": "system", "content": "<prompt de clasificación y resumen>"},
    {"role": "user", "content": "<description del caso>"}
  ],
  "temperature": 0,
  "max_tokens": 384,
  "stream": true,
  "stream_options": {"include_usage": true}
}
```

Cuando `USE_RESPONSE_FORMAT=true`, se agrega:

```json
{"response_format": {"type": "json_object"}}
```

El identificador local del caso no se incluye como campo independiente dentro del payload. Se conserva en el proceso local para relacionar cada respuesta con el caso de entrada. Las columnas de referencia, como la clasificación humana y el resumen de referencia, no se envían al modelo.

### Prueba de conectividad: `code/gateway_model_test.py`

La prueba usa `TEST_PROMPT` y construye un payload mínimo:

```json
{
  "model": "<MODEL_NAME>",
  "messages": [
    {"role": "user", "content": "<TEST_PROMPT>"}
  ],
  "temperature": 0,
  "max_tokens": 64
}
```

Esta prueba no envía casos PQRS. Sirve para comprobar endpoint, autenticación, TLS y respuesta básica del modelo.

## Ejecución

### 1. Probar conectividad

Desde la raíz del repositorio:

```bash
python code/evaluar_pqrs.py --connectivity-only
```

También puede ejecutarse el script mínimo:

```bash
python code/gateway_model_test.py
```

La salida informa el endpoint configurado, el modelo, el estado TLS, el código HTTP y el tiempo de respuesta. No imprime la clave API.

### 2. Ejecutar una muestra

Los archivos de entrada deben existir localmente. La entrada esperada es un JSONL con exactamente estos campos por línea:

```json
{"id": "caso-001", "description": "Texto anonimizado de la solicitud"}
```

Ejemplo de ejecución limitada:

```bash
python code/evaluar_pqrs.py \
  --input data/pqrs_gateway_input.jsonl \
  --output resultados/pqrs_gateway_results.jsonl \
  --limit 5
```

La ejecución guarda localmente, por caso:

- Identificador.
- Clasificación y resumen recuperados.
- Respuesta cruda del modelo.
- Latencia y TTFT.
- Tokens reportados, si están disponibles.
- Estado HTTP y error de parsing, si aplica.

Estos resultados están excluidos del repositorio mediante `resultados/`.

### 3. Calcular métricas localmente

El cálculo lee la referencia desde el XLSX local y las predicciones desde el JSONL local. No hace llamadas de red:

```bash
python code/calcular_metricas_pqrs.py
```

La salida genera en `metricas/`:

- `pqrs_classification_metrics.json`
- `pqrs_classification_detail.csv`

El detalle exportado contiene solo identificador, etiqueta real, predicción, corrección y validez. No copia `Nota`, `Resumen` ni `raw_output`.

La prueba interna del cálculo puede ejecutarse sin datos:

```bash
python code/calcular_metricas_pqrs.py --self-test
```

### 4. Generar el reporte HTML local

Después de calcular las métricas:

```bash
python code/generar_reporte_html_pqrs.py
```

El reporte se escribe en `metricas/reporte_evaluacion_pqrs.html` y usa únicamente el JSON de métricas local.

## Flujo de datos y límites

```text
Referencia PQRS local ──┐
                         ├─ evaluación local de métricas
Entrada JSONL local ────┤
                         │
                         └─ code/evaluar_pqrs.py
                                   │
                                   │ payload: model + messages + parámetros
                                   ▼
                         Gateway compatible con OpenAI
                                   │
                                   ▼
                         Respuesta JSON/SSE local
```

- La referencia humana no se envía al modelo.
- El payload de evaluación contiene `description` como mensaje de usuario.
- La API key se obtiene de `code/.env` o del entorno y se envía solo como encabezado.
- Las respuestas crudas se conservan localmente para auditoría y no se publican en este repositorio.
- La clasificación recuperada retirando un envoltorio Markdown debe reportarse separada del cumplimiento estricto de JSON.
- Una métrica de clasificación no demuestra por sí sola calidad de resumen, seguridad ni aptitud para producción.

## Resultados documentados

La evaluación consolidada está en:

`Docs/Linea_Base_Tecnica_Evaluacion_Qwen_32B_Casos_Bancarios_CONSOLIDADO.docx`

La presentación ejecutiva está en:

`Resultados de la evaluación de Qwen3-32B_con_PQRS.pptx`

La presentación documenta la comparación entre la línea base y el prompt con ejemplos sintéticos. Los resultados deben interpretarse junto con las limitaciones descritas en el documento consolidado y con los archivos de evidencia locales.

## Archivos excluidos

El `.gitignore` excluye de forma intencional:

- `data/`
- `resultados/`
- `metricas/`
- `fraude/`
- `code/.env`
- Cachés de Python y archivos locales de IDE/Windows.

No eliminar estas exclusiones para publicar datos de evaluación sin una revisión específica de privacidad y trazabilidad.

## Limitaciones conocidas

- La calidad del resumen requiere una evaluación separada de fidelidad, completitud y hechos.
- `response_format=json_object` no garantiza que el modelo entregue JSON estricto; debe validarse el schema recibido.
- Los ejemplos sintéticos pertenecen al prompt y no aumentan el número de casos reales evaluados.
- Las referencias humanas deben permanecer fuera del payload y conservarse con controles de acceso.
- La configuración y los umbrales de aceptación deben versionarse para comparar corridas de forma reproducible.
