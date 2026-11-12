#!/usr/bin/env python3


from __future__ import annotations

import json
import os
import ssl
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def load_dotenv() -> None:
    """Carga el .env junto al script sin sobrescribir variables existentes."""
    env_path = Path(__file__).resolve().with_name(".env")
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key.startswith("#"):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_dotenv()

GATEWAY_URL = os.getenv("GATEWAY_URL", "").strip()
API_KEY = os.getenv("GATEWAY_API_KEY", "").strip()
MODEL_NAME = os.getenv("MODEL_NAME", "").strip()
TIMEOUT = float(os.getenv("GATEWAY_TIMEOUT", "60"))
VERIFY_TLS = os.getenv("VERIFY_TLS", "true").strip().lower() not in {
    "0", "false", "no", "off"
}
PROMPT = os.getenv("TEST_PROMPT", "Responde únicamente: conexión exitosa")


def fail(message: str, exit_code: int = 2) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(exit_code)


def validate_config() -> None:
    missing = []
    if not GATEWAY_URL:
        missing.append("GATEWAY_URL")
    if not MODEL_NAME:
        missing.append("MODEL_NAME")
    if missing:
        fail("Faltan variables de configuración: " + ", ".join(missing))
    if not GATEWAY_URL.startswith(("http://", "https://")):
        fail("GATEWAY_URL debe comenzar por http:// o https://")
    if TIMEOUT <= 0:
        fail("GATEWAY_TIMEOUT debe ser mayor que cero")


def build_payload() -> bytes:
    # Contrato OpenAI-compatible.
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": PROMPT}],
        "temperature": 0,
        "max_tokens": 64,
    }
    return json.dumps(payload).encode("utf-8")


def parse_response(raw_body: bytes) -> str:
    text = raw_body.decode("utf-8", errors="replace")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text[:1000]

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        message = first.get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if content is not None:
            return str(content)
        if first.get("text") is not None:
            return str(first["text"])

    return json.dumps(data, ensure_ascii=False)[:1000]


def main() -> int:
    validate_config()

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "gateway-model-connection-test/1.0",
    }
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    request = Request(
        GATEWAY_URL,
        data=build_payload(),
        headers=headers,
        method="POST",
    )
    ssl_context = None if VERIFY_TLS else ssl._create_unverified_context()

    print(f"Endpoint: {GATEWAY_URL}")
    print(f"Modelo:   {MODEL_NAME}")
    print(f"TLS:      {'verificado' if VERIFY_TLS else 'NO verificado'}")
    print("Enviando solicitud...")

    started = time.perf_counter()
    try:
        with urlopen(request, timeout=TIMEOUT, context=ssl_context) as response:
            body = response.read()
            elapsed = time.perf_counter() - started
            print(f"HTTP:     {response.status}")
            print(f"Tiempo:   {elapsed:.2f} s")
            print("Respuesta:")
            print(parse_response(body))
            return 0 if 200 <= response.status < 300 else 1

    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        elapsed = time.perf_counter() - started
        print(f"HTTP:     {exc.code}")
        print(f"Tiempo:   {elapsed:.2f} s")
        print("Detalle del gateway:")
        print(body[:2000])
        return 1
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        print(f"ERROR DE RED: {reason}", file=sys.stderr)
        print("Revisa URL, DNS/VPN, proxy, firewall y certificado TLS.", file=sys.stderr)
        return 1
    except TimeoutError:
        print(f"TIMEOUT: no hubo respuesta en {TIMEOUT} segundos", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR INESPERADO: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
