"""Etapa 2-3: evaluar tool calling de Qwen3-32B contra un dataset de casos.

Uso:
    python 02_evaluar_tools.py --nivel 1 --limite 5      # piloto: 5 casos
    python 02_evaluar_tools.py --nivel 1
    python 02_evaluar_tools.py --nivel 2 --repeticiones 3

Cada ejecución guarda un CSV (una fila por solicitud) y un JSON con el resumen
de métricas en la carpeta resultados/.
"""
import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path

from cliente import MODELO, chat
from herramientas import HERRAMIENTAS_POR_NIVEL, SYSTEM_PROMPT

RAIZ = Path(__file__).parent
NINGUNA = "(ninguna)"


def normalizar_args(args):
    """Compara IDs sin importar mayúsculas ni espacios (sol-3310 == SOL-3310)."""
    if args is None:
        return None
    return {k: str(v).strip().upper() for k, v in args.items()}


def extraer_llamadas(mensaje):
    """Devuelve lista de (nombre, argumentos_dict | None si no es JSON válido)."""
    llamadas = []
    for tc in mensaje.get("tool_calls") or []:
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = None
        llamadas.append((fn.get("name"), args))
    return llamadas


def evaluar_caso(caso, tools):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": caso["entrada"]},
    ]
    respuesta, latencia, error = chat(messages, tools=tools, max_tokens=500)

    fila = {
        "id_caso": caso["id"],
        "modelo": MODELO,
        "entrada": caso["entrada"],
        "tool_esperada": caso["tool_esperada"] or NINGUNA,
        "args_esperados": json.dumps(caso["args_esperados"], ensure_ascii=False),
        "tool_seleccionada": "",
        "args_generados": "",
        "num_llamadas": 0,
        "tool_correcta": False,
        "args_correctos": "",
        "exito": False,
        "latencia_s": round(latencia, 3),
        "tokens_entrada": "",
        "tokens_salida": "",
        "error": error or "",
        "observacion": "",
    }
    if error:
        fila["tool_seleccionada"] = "ERROR"
        return fila

    mensaje = respuesta["choices"][0]["message"]
    uso = respuesta.get("usage") or {}
    fila["tokens_entrada"] = uso.get("prompt_tokens", "")
    fila["tokens_salida"] = uso.get("completion_tokens", "")

    llamadas = extraer_llamadas(mensaje)
    fila["num_llamadas"] = len(llamadas)
    contenido = mensaje.get("content") or ""

    if not llamadas:
        fila["tool_seleccionada"] = NINGUNA
        # Señal de que el gateway no convirtió el formato nativo de Qwen a tool_calls
        if re.search(r"<tool_call>|\"name\"\s*:\s*\"consultar_", contenido):
            fila["observacion"] = "Llamada a herramienta en texto, no en tool_calls (revisar compatibilidad)"
        else:
            fila["observacion"] = contenido[:200].replace("\n", " ")
    else:
        nombre, args = llamadas[0]
        fila["tool_seleccionada"] = nombre
        fila["args_generados"] = json.dumps(args, ensure_ascii=False) if args is not None else "JSON_INVALIDO"
        if len(llamadas) > 1:
            fila["observacion"] = f"Propuso {len(llamadas)} llamadas; se evalúa la primera"

    fila["tool_correcta"] = fila["tool_seleccionada"] == fila["tool_esperada"]

    if caso["tool_esperada"] is None:
        # El acierto es NO llamar herramientas
        fila["exito"] = fila["tool_correcta"]
    elif fila["tool_correcta"]:
        fila["args_correctos"] = normalizar_args(llamadas[0][1]) == normalizar_args(caso["args_esperados"])
        fila["exito"] = fila["args_correctos"] and len(llamadas) == 1
    return fila


def percentil(valores, p):
    if not valores:
        return None
    ordenados = sorted(valores)
    k = (len(ordenados) - 1) * p / 100
    i = int(k)
    j = min(i + 1, len(ordenados) - 1)
    return round(ordenados[i] + (ordenados[j] - ordenados[i]) * (k - i), 3)


def f1_macro(filas):
    """F1 macro sobre la selección de herramienta, incluyendo la clase 'ninguna'."""
    clases = {f["tool_esperada"] for f in filas}
    f1s = []
    for c in clases:
        tp = sum(f["tool_esperada"] == c and f["tool_seleccionada"] == c for f in filas)
        fp = sum(f["tool_esperada"] != c and f["tool_seleccionada"] == c for f in filas)
        fn = sum(f["tool_esperada"] == c and f["tool_seleccionada"] != c for f in filas)
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        f1s.append(2 * precision * recall / (precision + recall) if precision + recall else 0)
    return round(sum(f1s) / len(f1s), 3) if f1s else None


def resumir(filas):
    n = len(filas)
    con_tool_esperada = [f for f in filas if f["tool_esperada"] != NINGUNA and f["tool_correcta"]]
    latencias = [f["latencia_s"] for f in filas if not f["error"]]
    return {
        "modelo": MODELO,
        "solicitudes": n,
        "errores_api": sum(bool(f["error"]) for f in filas),
        "tool_selection_accuracy": round(sum(f["tool_correcta"] for f in filas) / n, 3),
        "argument_accuracy": (
            round(sum(f["args_correctos"] is True for f in con_tool_esperada) / len(con_tool_esperada), 3)
            if con_tool_esperada else None
        ),
        "task_success_rate": round(sum(f["exito"] for f in filas) / n, 3),
        "f1_macro_seleccion": f1_macro(filas),
        "latencia_p50_s": percentil(latencias, 50),
        "latencia_p95_s": percentil(latencias, 95),
        "tokens_entrada_total": sum(f["tokens_entrada"] or 0 for f in filas),
        "tokens_salida_total": sum(f["tokens_salida"] or 0 for f in filas),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--nivel", type=int, choices=sorted(HERRAMIENTAS_POR_NIVEL), default=1)
    parser.add_argument("--limite", type=int, help="Ejecutar solo los primeros N casos")
    parser.add_argument("--repeticiones", type=int, default=1, help="Veces que se repite cada caso")
    args = parser.parse_args()

    casos = json.loads((RAIZ / "casos" / f"nivel{args.nivel}.json").read_text(encoding="utf-8"))
    if args.limite:
        casos = casos[: args.limite]
    tools = HERRAMIENTAS_POR_NIVEL[args.nivel]

    total = len(casos) * args.repeticiones
    print(f"Nivel {args.nivel} | {len(casos)} casos x {args.repeticiones} repeticiones = {total} solicitudes\n")

    filas = []
    for rep in range(1, args.repeticiones + 1):
        for caso in casos:
            fila = evaluar_caso(caso, tools)
            fila = {"nivel": args.nivel, "repeticion": rep, **fila}
            filas.append(fila)
            estado = "OK  " if fila["exito"] else "FAIL"
            print(f"[{estado}] {fila['id_caso']} r{rep}  esperada={fila['tool_esperada']:<22} "
                  f"obtenida={fila['tool_seleccionada']:<22} {fila['latencia_s']}s")
            if fila["error"]:
                print(f"        {fila['error'][:200]}")
            if fila["error"] and "403" in fila["error"] and len(filas) == 1:
                print("\nError de autenticación en la primera solicitud; se detiene para no gastar más.")
                break
        else:
            continue
        break

    salida = RAIZ / "resultados"
    salida.mkdir(exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta_csv = salida / f"nivel{args.nivel}_{marca}.csv"
    with ruta_csv.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig para que Excel lea tildes
        writer = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        writer.writeheader()
        writer.writerows(filas)

    resumen = resumir(filas)
    (salida / f"nivel{args.nivel}_{marca}_resumen.json").write_text(
        json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("\n=== Resumen ===")
    for clave, valor in resumen.items():
        print(f"{clave:<26} {valor}")
    print(f"\nDetalle: {ruta_csv}")


if __name__ == "__main__":
    main()
