#!/usr/bin/env python3
"""Evalúa clasificación y resumen de PQRS contra un gateway OpenAI-compatible.

Modos:
    python PQRS/code/evaluar_pqrs.py --connectivity-only
    python PQRS/code/evaluar_pqrs.py --input data/pqrs_gateway_input.jsonl

El modo de evaluación envía únicamente id/description del JSONL. Las etiquetas
Clasificación y Resumen de referencia permanecen en el XLSX local y no forman
parte del payload.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ALLOWED_LABELS = {"Queja", "Petición", "Reclamo"}
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPOSITORY_ROOT / "data" / "pqrs_gateway_input.jsonl"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "resultados" / "pqrs_gateway_results.jsonl"


def load_dotenv() -> None:
    env_path = Path(__file__).resolve().with_name(".env")
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


load_dotenv()
GATEWAY_URL = os.getenv("GATEWAY_URL", "").strip()
API_KEY = os.getenv("GATEWAY_API_KEY", "").strip()
MODEL_NAME = os.getenv("MODEL_NAME", "").strip()
TIMEOUT = float(os.getenv("GATEWAY_TIMEOUT", "60"))
VERIFY_TLS = os.getenv("VERIFY_TLS", "true").strip().lower() not in {"0", "false", "no", "off"}
USE_RESPONSE_FORMAT = os.getenv("USE_RESPONSE_FORMAT", "false").strip().lower() in {"1", "true", "yes", "on"}


class GatewayError(RuntimeError):
    pass


def validate_config() -> None:
    missing = [name for name, value in (("GATEWAY_URL", GATEWAY_URL), ("MODEL_NAME", MODEL_NAME)) if not value]
    if missing:
        raise GatewayError("Faltan variables de configuración: " + ", ".join(missing))
    if not GATEWAY_URL.startswith(("http://", "https://")):
        raise GatewayError("GATEWAY_URL debe comenzar por http:// o https://")
    if TIMEOUT <= 0:
        raise GatewayError("GATEWAY_TIMEOUT debe ser mayor que cero")


def build_messages(description: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Clasifica y resume la solicitud según su intención principal. "
                "No clasifiques por la simple aparición de las palabras 'queja', "
                "'reclamo' o 'petición'; pueden usarse de forma coloquial y no "
                "necesariamente coincidir con la etiqueta correcta.\n\n"
                "Definiciones operativas:\n"
                "- Petición: solicitud de información, explicación, trámite, "
                "documento, actualización o acción, sin que predomine una "
                "inconformidad por una falla del producto, servicio, transacción "
                "o atención.\n"
                "- Reclamo: manifestación de inconformidad relacionada con un "
                "producto, servicio, transacción, cobro, pago, obligación o "
                "incumplimiento, en la que se solicita corrección, solución, "
                "reversión, reconocimiento o cumplimiento.\n"
                "- Queja: manifestación de inconformidad relacionada principalmente "
                "con la conducta, trato, atención o actuación de una persona, "
                "canal o proceso de atención.\n\n"
                "Reglas:\n"
                "1. Clasifica por la intención y el problema principal, no por "
                "palabras clave.\n"
                "2. Si dice 'presento una queja' pero describe un cobro incorrecto, "
                "pago pendiente, producto defectuoso o corrección de una operación, "
                "clasifica según el problema principal, normalmente Reclamo.\n"
                "3. Si dice 'reclamo' pero solo solicita información o explicación "
                "sin alegar falla o incumplimiento, clasifica como Petición.\n"
                "4. Si hay varias situaciones, usa la solicitud o el remedio "
                "principal.\n"
                "5. No agregues información que no esté en la solicitud.\n\n"
                "Ejemplos sintéticos de contraste:\n"
                "- Queja: 'El asesor me trató de manera irrespetuosa y se negó a "
                "atender mi solicitud.' La inconformidad principal es el trato o la "
                "atención de una persona.\n"
                "- Reclamo: 'Solicito corregir el cobro duplicado realizado en mi "
                "tarjeta.' La inconformidad principal es una operación, cobro o "
                "producto y se solicita una solución.\n"
                "- Petición: 'Necesito conocer los requisitos para actualizar mis "
                "datos.' Se solicita información o un trámite sin una inconformidad "
                "predominante.\n"
                "- Si una persona dice que presenta una queja, pero describe un "
                "cobro incorrecto, una transacción pendiente o un producto defectuoso, "
                "clasifica como Reclamo.\n"
                "- Si la inconformidad principal es por el trato, la conducta o la "
                "atención recibida, clasifica como Queja, aunque también solicite una "
                "respuesta.\n\n"
                "Responde únicamente con un objeto JSON válido, sin markdown ni "
                "texto adicional. Usa exactamente las claves classification y "
                "summary. classification debe ser exactamente una de: Queja, "
                "Petición, Reclamo. summary debe ser un resumen breve y fiel."
            ),
        },
        {"role": "user", "content": description},
    ]


def build_payload(messages: list[dict[str, str]], stream: bool) -> bytes:
    payload: dict[str, Any] = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 384,
    }
    if USE_RESPONSE_FORMAT:
        payload["response_format"] = {"type": "json_object"}
    if stream:
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def make_request(body: bytes) -> Request:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "pqrs-slm-evaluator/1.0",
    }
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    return Request(GATEWAY_URL, data=body, headers=headers, method="POST")


def ssl_context():
    return None if VERIFY_TLS else ssl._create_unverified_context()


def parse_json_content(text: str) -> tuple[str | None, str | None, str | None]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, None, f"respuesta_no_json: {exc}"
    if not isinstance(data, dict):
        return None, None, "respuesta_no_es_objeto"
    classification = data.get("classification")
    summary = data.get("summary")
    if not isinstance(classification, str):
        return None, None, "classification_ausente_o_invalida"
    if not isinstance(summary, str):
        return classification.strip(), None, "summary_ausente_o_invalido"
    classification = classification.strip()
    summary = summary.strip()
    if classification not in ALLOWED_LABELS:
        return classification, summary, "clasificacion_fuera_del_conjunto_permitido"
    if not summary:
        return classification, summary, "summary_vacio"
    return classification, summary, None


def send_non_stream(messages: list[dict[str, str]]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with urlopen(make_request(build_payload(messages, stream=False)), timeout=TIMEOUT, context=ssl_context()) as response:
            body = response.read()
            elapsed = time.perf_counter() - started
            data = json.loads(body.decode("utf-8", errors="replace"))
            return {"status": response.status, "elapsed": elapsed, "ttft": None, "data": data, "error": None}
    except HTTPError as exc:
        elapsed = time.perf_counter() - started
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        return {"status": exc.code, "elapsed": elapsed, "ttft": None, "data": None, "error": detail}
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {"status": None, "elapsed": time.perf_counter() - started, "ttft": None, "data": None, "error": f"{type(exc).__name__}: {exc}"}


def send_stream(messages: list[dict[str, str]]) -> dict[str, Any]:
    started = time.perf_counter()
    first_token = None
    parts: list[str] = []
    usage: dict[str, Any] = {}
    finish_reason = None
    try:
        with urlopen(make_request(build_payload(messages, stream=True)), timeout=TIMEOUT, context=ssl_context()) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                raw_chunk = line[5:].strip()
                if raw_chunk == "[DONE]":
                    break
                chunk = json.loads(raw_chunk)
                usage = chunk.get("usage") or usage
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    if first_token is None and content:
                        first_token = time.perf_counter() - started
                    if content:
                        parts.append(content)
                    finish_reason = choice.get("finish_reason") or finish_reason
        elapsed = time.perf_counter() - started
        return {
            "status": response.status,
            "elapsed": elapsed,
            "ttft": first_token,
            "text": "".join(parts),
            "usage": usage,
            "finish_reason": finish_reason,
            "error": None,
        }
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        return {"status": exc.code, "elapsed": time.perf_counter() - started, "ttft": first_token, "text": "", "usage": {}, "error": detail}
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {"status": None, "elapsed": time.perf_counter() - started, "ttft": first_token, "text": "", "usage": {}, "error": f"{type(exc).__name__}: {exc}"}


def extract_non_stream(data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    choices = data.get("choices") or []
    if not choices:
        raise GatewayError("respuesta_sin_choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if content is None:
        raise GatewayError("respuesta_sin_message_content")
    return str(content), data.get("usage") or {}


def read_cases(path: Path, limit: int | None) -> list[dict[str, str]]:
    cases = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            case = json.loads(line)
            if set(case) != {"id", "description"}:
                raise ValueError(f"Caso {line_number}: campos inesperados")
            if not str(case["id"]).strip() or not str(case["description"]).strip():
                raise ValueError(f"Caso {line_number}: id o description vacío")
            cases.append({"id": str(case["id"]), "description": str(case["description"])})
            if limit is not None and len(cases) >= limit:
                break
    return cases


def connectivity_only() -> int:
    validate_config()
    prompt = os.getenv("TEST_PROMPT", "Responde únicamente: conexión exitosa")
    result = send_non_stream([{"role": "user", "content": prompt}])
    print(f"Endpoint configurado: {GATEWAY_URL}")
    print(f"Modelo configurado: {MODEL_NAME}")
    print(f"TLS: {'verificado' if VERIFY_TLS else 'NO verificado'}")
    print(f"HTTP: {result['status']}")
    print(f"Tiempo: {result['elapsed']:.2f} s")
    if result["error"]:
        print(f"ERROR_GATEWAY: {result['error']}", file=sys.stderr)
        return 1
    print("CONECTIVIDAD_OK")
    return 0


def evaluate(input_path: Path, output_path: Path, limit: int | None, stream: bool) -> int:
    validate_config()
    cases = read_cases(input_path, limit)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for case in cases:
            if stream:
                response = send_stream(build_messages(case["description"]))
                raw_text = response.get("text", "")
                usage = response.get("usage", {})
            else:
                response = send_non_stream(build_messages(case["description"]))
                raw_text, usage = "", {}
                if response["data"] is not None:
                    try:
                        raw_text, usage = extract_non_stream(response["data"])
                    except GatewayError as exc:
                        response["error"] = str(exc)
            classification = summary = parse_error = None
            if raw_text:
                classification, summary, parse_error = parse_json_content(raw_text)
            result = {
                "id": case["id"],
                "classification": classification,
                "summary": summary,
                "raw_output": raw_text,
                "valid_classification": classification in ALLOWED_LABELS,
                "latency_ms": round(response["elapsed"] * 1000, 3),
                "ttft_ms": round(response["ttft"] * 1000, 3) if response.get("ttft") is not None else None,
                "usage": usage,
                "http_status": response.get("status"),
                "error": response.get("error") or parse_error,
            }
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
    print(f"RESULTADOS_GUARDADOS={output_path}")
    print(f"CASOS_PROCESADOS={len(cases)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connectivity-only", action="store_true", help="Prueba el gateway sin enviar PQRS.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--no-stream", action="store_true", help="Desactiva streaming durante la evaluación.")
    args = parser.parse_args()
    try:
        if args.connectivity_only:
            return connectivity_only()
        return evaluate(args.input, args.output, args.limit, stream=not args.no_stream)
    except (GatewayError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
