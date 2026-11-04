"""Métricas de la línea base técnica (sección 4, matriz maestra) calculadas sobre las ejecuciones.

Automáticas: Q02, Q03, Q04 (preliminar, sin Q01), S01, A01, P01, P02, P03, P04, E01.
Q01 y Q04 definitiva requieren la rúbrica humana (ver calcular_rubrica.py).
Las ejecuciones fallidas NO se excluyen: cuentan como no aceptables y con completitud 0.
"""
from collections import defaultdict
from statistics import mean, pstdev

NINGUNA = "ninguna"


def percentil(valores, p):
    if not valores:
        return None
    ordenados = sorted(valores)
    k = (len(ordenados) - 1) * p / 100
    i = int(k)
    j = min(i + 1, len(ordenados) - 1)
    return round(ordenados[i] + (ordenados[j] - ordenados[i]) * (k - i), 3)


def _pct(parte, total):
    return round(100 * parte / total, 1) if total else None


def _media(valores):
    valores = [v for v in valores if v is not None]
    return round(mean(valores), 1) if valores else None


def calidad(filas):
    """Q02, Q03, Q04 (preliminar) y S01."""
    n = len(filas)
    return {
        "ejecuciones": n,
        "Q02_completitud_media": _media([f["q02_completitud"] for f in filas]),
        "Q02_casos_completos_pct": _pct(sum(f["q02_completitud"] == 100 for f in filas), n),
        "Q03_fidelidad_media": _media([f["q03_fidelidad"] for f in filas]),
        "Q03_ejecuciones_con_citas": sum(f["citas_total"] > 0 for f in filas),
        "Q04_aceptacion_preliminar_pct": _pct(sum(f["aceptable_preliminar"] for f in filas), n),
        "S01_errores_criticos_pct": _pct(sum(f["error_critico"] for f in filas), n),
    }


def herramientas(filas):
    """A01: llamadas correctas / oportunidades aplicables, y argumentos válidos."""
    oportunidades = [f for f in filas if f["tool_esperada"] != NINGUNA]
    sin_tool = [f for f in filas if f["tool_esperada"] == NINGUNA]
    tool_ok = [f for f in oportunidades if f["tool_seleccionada"] == f["tool_esperada"]]
    return {
        "A01_oportunidades": len(oportunidades),
        "A01_llamadas_correctas_pct": _pct(len(tool_ok), len(oportunidades)),
        "A01_argumentos_validos_pct": _pct(sum(f["args_correctos"] for f in tool_ok), len(tool_ok)),
        "A01_exito_completo_pct": _pct(sum(f["tool_seleccionada"] == f["tool_esperada"] and f["args_correctos"]
                                           for f in oportunidades), len(oportunidades)),
        "A01_llamadas_innecesarias_pct": _pct(sum(f["tool_seleccionada"] not in (NINGUNA, "ERROR") for f in sin_tool),
                                              len(sin_tool)),
        "A01_llamadas_en_texto": sum(f["llamada_en_texto"] for f in filas),
    }


def rendimiento(filas, duracion_total_s):
    """P01 latencia, P02 TTFT, P03 velocidad de generación y P04 capacidad y fallos."""
    ok = [f for f in filas if f["estado"] in ("ok", "truncado")]
    latencias = [f["latencia_s"] for f in ok]
    ttfts = [f["ttft_s"] for f in ok if f["ttft_s"] is not None]
    velocidades = [f["tokens_por_s"] for f in ok if f["tokens_por_s"] is not None]
    return {
        "P01_latencia_p50_s": percentil(latencias, 50),
        "P01_latencia_p95_s": percentil(latencias, 95),
        "P01_latencia_media_s": round(mean(latencias), 3) if latencias else None,
        "P02_ttft_p50_s": percentil(ttfts, 50),
        "P02_ttft_p95_s": percentil(ttfts, 95),
        "P03_tokens_por_s_media": round(mean(velocidades), 1) if velocidades else None,
        "P04_solicitudes_por_min": round(60 * len(filas) / duracion_total_s, 1) if duracion_total_s else None,
        "P04_errores_http": sum(f["estado"] == "error_http" for f in filas),
        "P04_timeouts": sum(f["estado"] == "timeout" for f in filas),
        "P04_otros_errores": sum(f["estado"] == "error" for f in filas),
        "P04_truncados": sum(f["estado"] == "truncado" for f in filas),
        "tokens_entrada_total": sum(f["tokens_entrada"] or 0 for f in filas),
        "tokens_salida_total": sum(f["tokens_salida"] or 0 for f in filas),
    }


def consistencia(filas):
    """E01: variación entre repeticiones del mismo caso (solo si hay ≥2 repeticiones)."""
    por_caso = defaultdict(list)
    for f in filas:
        por_caso[f["case_id"]].append(f)
    repetidos = {c: fs for c, fs in por_caso.items() if len(fs) > 1}
    if not repetidos:
        return {"E01_casos_repetidos": 0}
    estables, contradicciones, desviaciones = 0, [], []
    for caso, fs in repetidos.items():
        decisiones = {(f["tool_seleccionada"], f["aceptable_preliminar"], f["error_critico"]) for f in fs}
        if len(decisiones) == 1:
            estables += 1
        else:
            contradicciones.append(caso)
        desviaciones.append(pstdev([f["q02_completitud"] for f in fs]))
    return {
        "E01_casos_repetidos": len(repetidos),
        "E01_decision_estable_pct": _pct(estables, len(repetidos)),
        "E01_desviacion_q02_media": round(mean(desviaciones), 2),
        "E01_casos_con_contradicciones": contradicciones,
    }


def resumir(filas, duracion_total_s):
    resumen = {
        "global": {**calidad(filas), **herramientas(filas), **rendimiento(filas, duracion_total_s), **consistencia(filas)},
    }
    for dimension in ("escenario", "dificultad", "norma_id"):
        grupos = defaultdict(list)
        for f in filas:
            grupos[f[dimension]].append(f)
        resumen[f"por_{dimension}"] = {
            valor: {**calidad(fs), **({k: v for k, v in herramientas(fs).items()} if dimension == "escenario" else {})}
            for valor, fs in sorted(grupos.items())
        }
    return resumen
