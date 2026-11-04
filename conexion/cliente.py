"""Cliente mínimo para el gateway LiteLLM (API compatible con OpenAI).

Solo usa la librería estándar de Python, no requiere instalar nada.
"""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


def cargar_env(ruta=Path(__file__).parent / ".env"):
    """Carga variables KEY=VALOR desde .env sin sobrescribir las ya definidas."""
    if not ruta.exists():
        raise SystemExit(f"No existe {ruta}. Copia .env.example como .env y completa la API key.")
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip())


cargar_env()
BASE_URL = os.environ["LITELLM_BASE_URL"].rstrip("/")
API_KEY = os.environ["LITELLM_API_KEY"]
MODELO = os.environ.get("MODELO", "qwen.qwen3-32b-v1:0")
TIMEOUT = float(os.environ.get("TIMEOUT_SEGUNDOS", "60"))


def chat(messages, tools=None, max_tokens=300, temperature=0):
    """Envía una solicitud a /v1/chat/completions.

    Devuelve (respuesta_json | None, latencia_segundos, error | None).
    """
    cuerpo = {
        "model": MODELO,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        cuerpo["tools"] = tools
        cuerpo["tool_choice"] = "auto"

    req = urllib.request.Request(
        f"{BASE_URL}/v1/chat/completions",
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    inicio = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            datos = json.loads(resp.read().decode("utf-8"))
        return datos, time.perf_counter() - inicio, None
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", errors="replace")
        return None, time.perf_counter() - inicio, f"HTTP {e.code}: {detalle[:500]}"
    except Exception as e:  # timeout, DNS, conexión rechazada, etc.
        return None, time.perf_counter() - inicio, f"{type(e).__name__}: {e}"


def chat_stream(messages, tools=None, max_tokens=300, temperature=0):
    """Igual que chat(), pero con streaming para medir el tiempo hasta el primer token (TTFT).

    Reconstruye una respuesta con la misma forma que la no-streaming.
    Devuelve (respuesta_json | None, latencia_segundos, ttft_segundos | None, error | None).
    """
    cuerpo = {
        "model": MODELO,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if tools:
        cuerpo["tools"] = tools
        cuerpo["tool_choice"] = "auto"

    req = urllib.request.Request(
        f"{BASE_URL}/v1/chat/completions",
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    inicio = time.perf_counter()
    ttft = None
    contenido, llamadas, uso, finish_reason = [], {}, {}, None
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            for linea in resp:
                linea = linea.decode("utf-8").strip()
                if not linea.startswith("data:"):
                    continue
                dato = linea[5:].strip()
                if dato == "[DONE]":
                    break
                chunk = json.loads(dato)
                uso = chunk.get("usage") or uso
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    if ttft is None and (delta.get("content") or delta.get("tool_calls")):
                        ttft = time.perf_counter() - inicio
                    if delta.get("content"):
                        contenido.append(delta["content"])
                    for tc in delta.get("tool_calls") or []:
                        actual = llamadas.setdefault(tc.get("index", 0), {"name": "", "arguments": ""})
                        fn = tc.get("function") or {}
                        actual["name"] += fn.get("name") or ""
                        actual["arguments"] += fn.get("arguments") or ""
                    finish_reason = choice.get("finish_reason") or finish_reason
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", errors="replace")
        return None, time.perf_counter() - inicio, ttft, f"HTTP {e.code}: {detalle[:500]}"
    except Exception as e:  # timeout, DNS, conexión rechazada, etc.
        return None, time.perf_counter() - inicio, ttft, f"{type(e).__name__}: {e}"

    mensaje = {"role": "assistant", "content": "".join(contenido) or None}
    if llamadas:
        mensaje["tool_calls"] = [
            {"type": "function", "function": llamadas[i]} for i in sorted(llamadas)
        ]
    respuesta = {"choices": [{"message": mensaje, "finish_reason": finish_reason}], "usage": uso}
    return respuesta, time.perf_counter() - inicio, ttft, None
