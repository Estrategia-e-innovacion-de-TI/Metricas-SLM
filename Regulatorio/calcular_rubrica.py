"""Calcula Q01, Q04 definitiva y S01 confirmado a partir de la rúbrica llenada por expertos.

Uso:
    python calcular_rubrica.py resultados/regulatorio_<fecha>_rubrica.csv

Rúbrica (línea base, sección 5): seis dimensiones calificadas 0–4 o NA.
    Q01 = Σ (peso_i × nota_i / 4) × 100, renormalizando pesos si alguna dimensión es NA.
    Aceptable (Q04) = Q01 ≥ 80, elementos_completos = si y error_critico_confirmado = no.
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

PESOS = {"exactitud": 25, "completitud": 20, "fidelidad": 20, "pertinencia": 15, "claridad": 10, "incertidumbre": 10}
UMBRAL_CALIDAD = 80


def q01(fila):
    """Devuelve el puntaje 0–100, o None si la fila aún no está calificada."""
    notas = {}
    for dimension, peso in PESOS.items():
        valor = (fila.get(dimension) or "").strip().upper()
        if valor == "NA":
            continue
        if valor == "":
            return None
        nota = float(valor.replace(",", "."))
        if not 0 <= nota <= 4:
            raise ValueError(f"{fila['case_id']} r{fila['repeticion']}: {dimension}={valor} fuera de 0–4")
        notas[dimension] = nota
    peso_total = sum(PESOS[d] for d in notas)
    if not peso_total:
        return None
    return round(sum(PESOS[d] * n / 4 for d, n in notas.items()) * 100 / peso_total, 1)


def si(valor):
    return (valor or "").strip().lower() in ("si", "sí", "s", "1", "true")


def resumir(filas):
    calificadas = [f for f in filas if f["_q01"] is not None]
    n = len(calificadas)
    return {
        "ejecuciones": len(filas),
        "calificadas": n,
        "pendientes": len(filas) - n,
        "Q01_calidad_media": round(sum(f["_q01"] for f in calificadas) / n, 1) if n else None,
        "Q04_aceptacion_pct": round(100 * sum(f["_aceptable"] for f in calificadas) / n, 1) if n else None,
        "S01_errores_criticos_confirmados_pct": round(100 * sum(si(f["error_critico_confirmado"]) for f in calificadas) / n, 1)
        if n else None,
    }


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    ruta = Path(sys.argv[1])
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))

    for f in filas:
        f["_q01"] = q01(f)
        f["_aceptable"] = (f["_q01"] is not None and f["_q01"] >= UMBRAL_CALIDAD
                           and si(f["elementos_completos"]) and not si(f["error_critico_confirmado"]))

    resultado = {"global": resumir(filas)}
    for dimension in ("escenario", "dificultad", "norma"):
        grupos = defaultdict(list)
        for f in filas:
            grupos[f[dimension]].append(f)
        resultado[f"por_{dimension}"] = {k: resumir(v) for k, v in sorted(grupos.items())}

    destino = ruta.with_name(ruta.stem + "_resultado.json")
    destino.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resultado["global"], indent=2, ensure_ascii=False))
    print(f"\nDetalle por escenario, dificultad y norma: {destino}")


if __name__ == "__main__":
    main()
