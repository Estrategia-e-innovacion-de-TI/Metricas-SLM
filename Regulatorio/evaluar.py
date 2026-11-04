"""Evalúa Qwen3-32B con el dataset regulatorio y calcula las métricas de la línea base técnica.

Uso:
    python evaluar.py --modo-referencia                  # calibración sin API: responde con la salida esperada
    python evaluar.py --limite 5                         # piloto: 5 casos
    python evaluar.py --escenario "Tool calling"         # un solo escenario (20 casos)
    python evaluar.py --repeticiones 3                   # protocolo completo: 100 x 3 = 300 solicitudes
    python evaluar.py --limite 20 --concurrencia 5       # prueba de carga (P04)

Genera en resultados/:
    regulatorio_<fecha>_ejecuciones.csv   una fila por ejecución (entidad "Ejecución" de la línea base)
    regulatorio_<fecha>_resumen.json      run + métricas globales y por escenario, dificultad y norma
    regulatorio_<fecha>_rubrica.csv       plantilla para la evaluación experta (Q01 y Q04 definitiva)
"""
import argparse
import csv
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from herramientas_regulatorias import FORMATO, HERRAMIENTAS, SYSTEM_PROMPT, construir_mensajes
from metricas import NINGUNA, resumir
from verificaciones import limpiar_respuesta, normalizar_args, verificar

RAIZ = Path(__file__).parent
DATASET = RAIZ / "dataset_regulacion_colombia_100_casos.csv"
DIMENSIONES_RUBRICA = ["exactitud", "completitud", "fidelidad", "pertinencia", "claridad", "incertidumbre"]


def cargar_casos(escenario=None, limite=None):
    with DATASET.open(encoding="utf-8-sig", newline="") as f:
        casos = list(csv.DictReader(f))
    if escenario:
        casos = [c for c in casos if c["escenario"] == escenario]
        if not casos:
            raise SystemExit(f"No hay casos del escenario {escenario!r}")
    return casos[:limite] if limite else casos


def respuesta_referencia(caso):
    """Simula una respuesta perfecta a partir de la salida esperada (sin llamar a la API)."""
    esperado = json.loads(caso["salida_esperada_json"])
    if caso["tool_esperada"] != NINGUNA:
        llamada = {"type": "function", "function": {"name": esperado["tool"], "arguments": json.dumps(esperado["arguments"])}}
        mensaje = {"content": None, "tool_calls": [llamada]}
    else:
        mensaje = {"content": json.dumps(esperado, ensure_ascii=False)}
    return {"choices": [{"message": mensaje, "finish_reason": "stop"}], "usage": {}}, 0.0, None, None


def extraer_llamadas(mensaje):
    llamadas = []
    for tc in mensaje.get("tool_calls") or []:
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = None
        llamadas.append((fn.get("name"), args))
    return llamadas


def clasificar_estado(error, finish_reason):
    if error:
        if error.startswith("HTTP"):
            return "error_http"
        if "timed out" in error.lower() or "timeout" in error.lower():
            return "timeout"
        return "error"
    return "truncado" if finish_reason == "length" else "ok"


def ejecutar(caso, repeticion, run_id, llamar, max_tokens):
    mensajes = construir_mensajes(caso)
    respuesta, latencia, ttft, error = llamar(caso, mensajes, max_tokens)

    contenido, llamadas, finish_reason, uso = "", [], None, {}
    if respuesta:
        choice = respuesta["choices"][0]
        contenido = choice["message"].get("content") or ""
        llamadas = extraer_llamadas(choice["message"])
        finish_reason = choice.get("finish_reason")
        uso = respuesta.get("usage") or {}
    estado = clasificar_estado(error, finish_reason)

    v = verificar(caso, contenido, llamadas)
    tool = llamadas[0][0] if llamadas else (NINGUNA if not error else "ERROR")
    args_ok = bool(llamadas) and normalizar_args(llamadas[0][1]) == normalizar_args(json.loads(caso["argumentos_esperados_json"]))
    tokens_salida = uso.get("completion_tokens")
    generacion = latencia - ttft if ttft is not None else None
    if error:  # sin respuesta no hay elementos cubiertos
        v["q02_completitud"], v["elementos_cubiertos"] = 0.0, 0

    return {
        "run_id": run_id,
        "case_id": caso["case_id"],
        "repeticion": repeticion,
        "escenario": caso["escenario"],
        "dificultad": caso["dificultad"],
        "norma_id": caso["norma_id"],
        "input_hash": hashlib.sha256(json.dumps(mensajes, ensure_ascii=False).encode()).hexdigest()[:16],
        "tool_esperada": caso["tool_esperada"],
        "tool_seleccionada": tool,
        "args_generados": json.dumps(llamadas[0][1], ensure_ascii=False) if llamadas else "",
        "args_correctos": args_ok,
        "llamada_en_texto": v["llamada_en_texto"],
        "elementos_cubiertos": v["elementos_cubiertos"],
        "elementos_aplicables": v["elementos_aplicables"],
        "elementos_fallidos": "; ".join(n for n, ok in v["elementos"] if not ok),
        "q02_completitud": v["q02_completitud"],
        "citas_soportadas": v["citas_soportadas"],
        "citas_total": v["citas_total"],
        "q03_fidelidad": v["q03_fidelidad"],
        "error_critico": bool(v["criticos"]),
        "errores_criticos_detectados": "; ".join(v["criticos"]),
        "aceptable_preliminar": estado == "ok" and v["q02_completitud"] == 100 and not v["criticos"],
        "estado": estado,
        "finish_reason": finish_reason or "",
        "latencia_s": round(latencia, 3),
        "ttft_s": round(ttft, 3) if ttft is not None else None,
        "tokens_entrada": uso.get("prompt_tokens"),
        "tokens_salida": tokens_salida,
        "tokens_por_s": round(tokens_salida / generacion, 1) if tokens_salida and generacion and generacion > 0 else None,
        "error": error or "",
        "output": limpiar_respuesta(contenido),
        "_caso": caso,
    }


def escribir_csv(ruta, filas, campos):
    with ruta.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig para que Excel lea tildes
        writer = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(filas)


def plantilla_rubrica(filas):
    """Una fila por ejecución para que el experto califique las seis dimensiones (0–4 o NA)."""
    salida = []
    for f in filas:
        c = f["_caso"]
        salida.append({
            "run_id": f["run_id"], "case_id": f["case_id"], "repeticion": f["repeticion"],
            "escenario": f["escenario"], "dificultad": f["dificultad"], "norma": c["norma"],
            "entrada": c["entrada"], "contexto_autorizado": c["contexto_autorizado"],
            "salida_esperada": c["salida_esperada_json"], "elementos_obligatorios": c["elementos_obligatorios"],
            "error_critico_definido": c["error_critico"],
            "respuesta_modelo": f["output"] or (f"[herramienta] {f['tool_seleccionada']} {f['args_generados']}"
                                                if f["tool_seleccionada"] not in (NINGUNA, "ERROR") else f["error"]),
            "auto_q02": f["q02_completitud"], "auto_elementos_fallidos": f["elementos_fallidos"],
            "auto_criticos": f["errores_criticos_detectados"],
            **{d: "" for d in DIMENSIONES_RUBRICA},
            "elementos_completos": "si" if f["q02_completitud"] == 100 else "no",
            "error_critico_confirmado": "",
            "evaluador": "", "evidencia_comentario": "",
        })
    return salida


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limite", type=int, help="Ejecutar solo los primeros N casos")
    parser.add_argument("--escenario", help="Filtrar por escenario (p. ej. 'Tool calling')")
    parser.add_argument("--repeticiones", type=int, default=1, help="Repeticiones por caso (la línea base pide 3)")
    parser.add_argument("--concurrencia", type=int, default=1, help="Solicitudes en paralelo (P04)")
    parser.add_argument("--max-tokens", type=int, default=800)
    parser.add_argument("--sin-streaming", action="store_true", help="No mide TTFT (P02) ni velocidad (P03)")
    parser.add_argument("--modo-referencia", action="store_true",
                        help="No llama a la API: responde con la salida esperada para calibrar las verificaciones")
    args = parser.parse_args()

    casos = cargar_casos(args.escenario, args.limite)
    if args.modo_referencia:
        modelo, base_url = "referencia (salida esperada)", "-"
        llamar = lambda caso, mensajes, max_tokens: respuesta_referencia(caso)  # noqa: E731
    else:
        sys.path.insert(0, str(RAIZ.parent / "conexion"))
        from cliente import BASE_URL, MODELO, chat, chat_stream

        modelo, base_url = MODELO, BASE_URL
        if args.sin_streaming:
            def llamar(caso, mensajes, max_tokens):
                respuesta, latencia, error = chat(mensajes, tools=HERRAMIENTAS, max_tokens=max_tokens)
                return respuesta, latencia, None, error
        else:
            def llamar(caso, mensajes, max_tokens):
                return chat_stream(mensajes, tools=HERRAMIENTAS, max_tokens=max_tokens)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    prompt_version = hashlib.sha256((SYSTEM_PROMPT + json.dumps(FORMATO, ensure_ascii=False)).encode()).hexdigest()[:12]
    trabajos = [(caso, rep) for rep in range(1, args.repeticiones + 1) for caso in casos]
    print(f"Run {run_id} | modelo {modelo} | {len(casos)} casos x {args.repeticiones} rep = {len(trabajos)} solicitudes"
          f" | concurrencia {args.concurrencia}\n")

    inicio = time.perf_counter()
    filas = []
    with ThreadPoolExecutor(max_workers=args.concurrencia) as pool:
        futuros = [pool.submit(ejecutar, caso, rep, run_id, llamar, args.max_tokens) for caso, rep in trabajos]
        for futuro in futuros:
            fila = futuro.result()
            filas.append(fila)
            marca = "OK  " if fila["aceptable_preliminar"] else ("ERR " if fila["error"] else "FAIL")
            print(f"[{marca}] {fila['case_id']} r{fila['repeticion']} {fila['escenario']:<26} "
                  f"Q02={fila['q02_completitud']:>5} critico={'si' if fila['error_critico'] else 'no'} "
                  f"{fila['latencia_s']}s")
            if fila["error"]:
                print(f"        {fila['error'][:200]}")
            if fila["estado"] == "error_http" and len(filas) == 1 and ("401" in fila["error"] or "403" in fila["error"]):
                print("\nError de autenticación en la primera solicitud; se cancela para no gastar más.")
                for pendiente in futuros:
                    pendiente.cancel()
                break
    duracion = time.perf_counter() - inicio

    salida = RAIZ / "resultados"
    salida.mkdir(exist_ok=True)
    base = salida / f"regulatorio_{run_id}"
    campos = [k for k in filas[0] if k != "_caso"]
    escribir_csv(base.with_name(base.name + "_ejecuciones.csv"), filas, campos)
    rubrica = plantilla_rubrica(filas)
    escribir_csv(base.with_name(base.name + "_rubrica.csv"), rubrica, list(rubrica[0]))

    resumen = {
        "run": {
            "run_id": run_id, "fecha": datetime.now().isoformat(timespec="seconds"), "modelo_id": modelo,
            "endpoint": base_url, "prompt_version": prompt_version,
            "dataset_version": casos[0]["version_dataset"], "dataset": DATASET.name,
            "config": {"temperature": 0, "max_tokens": args.max_tokens, "streaming": not args.sin_streaming,
                       "concurrencia": args.concurrencia, "repeticiones": args.repeticiones},
            "duracion_s": round(duracion, 1),
            "nota": "Q02/Q03/S01 son verificaciones automáticas preliminares; Q01 y Q04 definitiva requieren rúbrica experta.",
        },
        **resumir(filas, duracion),
    }
    base.with_name(base.name + "_resumen.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== Métricas globales ===")
    for clave, valor in resumen["global"].items():
        print(f"{clave:<34} {valor}")
    print("\n=== Por escenario (Q02 media | Q04 prelim. | S01) ===")
    for esc, m in resumen["por_escenario"].items():
        print(f"{esc:<26} {m['Q02_completitud_media']:>6} | {m['Q04_aceptacion_preliminar_pct']:>6}% | {m['S01_errores_criticos_pct']:>5}%")
    print(f"\nArchivos: {base.name}_ejecuciones.csv, _resumen.json, _rubrica.csv en {salida}")


if __name__ == "__main__":
    main()
