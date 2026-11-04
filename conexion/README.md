# conexion — Conexión y tool calling con Qwen3-32B

Prueba sencilla de Qwen3-32B (`qwen.qwen3-32b-v1:0`) en Amazon Bedrock, a través del gateway LiteLLM.
Usa solo la librería estándar de Python 3.10+; no hay que instalar nada.

```
Script Python  ->  LiteLLM Gateway  ->  Amazon Bedrock (Qwen3-32B)
```

Todos los comandos se ejecutan dentro de esta carpeta (`cd conexion`).

## Configuración

1. Copia `.env.example` como `.env`.
2. Pon en `LITELLM_API_KEY` una API key **vigente**. La que se compartió por chat ya quedó expuesta, así que hay que revocarla y pedir otra.

## Etapa 1 — Conectividad

```
python 01_conectividad.py
```

Si responde `Bearer Token has expired` (HTTP 403), lo que está vencido es la credencial LiteLLM → Bedrock y la debe renovar el equipo del gateway. Una API key nueva de LiteLLM no lo soluciona por sí sola.

## Etapa 2 — Tool calling (niveles 1 y 2)

```
python 02_evaluar_tools.py --nivel 1 --limite 5      # piloto, 5 solicitudes
python 02_evaluar_tools.py --nivel 1                 # 10 casos, 1 herramienta
python 02_evaluar_tools.py --nivel 2                 # 10 casos, 3 herramientas
python 02_evaluar_tools.py --nivel 1 --repeticiones 3
```

El modelo solo **propone** la llamada (no se ejecuta ninguna herramienta). Se compara la herramienta y los argumentos propuestos contra lo esperado en `casos/nivelN.json`. Cada nivel incluye casos donde lo correcto es **no** llamar herramientas (falta el ID, saludo o una pregunta fuera de alcance).

Si aparece la observación *"Llamada a herramienta en texto, no en tool_calls"*, el modelo intentó llamar la herramienta pero LiteLLM/Bedrock no lo convirtió al formato estándar. Eso es un problema de compatibilidad que hay que reportar.

## Resultados

En `resultados/` queda:
- `nivelN_<fecha>.csv`: una fila por solicitud (tool esperada y seleccionada, argumentos, éxito, latencia, tokens, error). Se abre en Excel.
- `nivelN_<fecha>_resumen.json`: tool selection accuracy, argument accuracy, task success rate, F1 macro (incluyendo "ninguna"), latencia P50/P95 y tokens totales.

El costo se calcula aparte, con los tokens totales y el precio que reporte LiteLLM/Bedrock.

## Presupuesto (USD 10/semana)

Plan inicial ≈ 63 solicitudes: 3 de conectividad + 10 casos nivel 1 + 10 casos nivel 2, y 2 repeticiones extra de cada caso. Antes de ampliar, revisen el consumo real en LiteLLM.

## Estructura

| Archivo | Para qué |
|---|---|
| `cliente.py` | Carga `.env` y hace la llamada HTTP a `/v1/chat/completions` |
| `01_conectividad.py` | Etapa 1 |
| `herramientas.py` | Herramientas simuladas y system prompt |
| `casos/nivel1.json`, `casos/nivel2.json` | Datasets con resultados esperados |
| `02_evaluar_tools.py` | Ejecuta los casos y calcula las métricas |

Para agregar casos, edita los JSON. Para agregar herramientas, edita `herramientas.py`.
