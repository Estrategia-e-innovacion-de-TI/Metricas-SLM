#!/usr/bin/env python3
"""Genera un reporte HTML local a partir del JSON de métricas PQRS."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "metricas" / "pqrs_classification_metrics.json"
DEFAULT_OUTPUT = ROOT / "metricas" / "reporte_evaluacion_pqrs.html"


def pct(value: float | None) -> str:
    return "N/D" if value is None else f"{value * 100:.2f}%"


def num(value: float | int | None, decimals: int = 2) -> str:
    return "N/D" if value is None else f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def conclusion(text: str, tone: str = "neutral") -> str:
    return f'<div class="conclusion {tone}"><span>Conclusión</span><p>{html.escape(text)}</p></div>'


def card(title: str, eyebrow: str, body: str, conclusion_text: str, tone: str = "neutral") -> str:
    return f'''<article class="card">
      <div class="eyebrow">{html.escape(eyebrow)}</div>
      <h2>{html.escape(title)}</h2>
      <div class="card-body">{body}</div>
      {conclusion(conclusion_text, tone)}
    </article>'''


def table_rows(per_class: dict[str, dict[str, float | int]]) -> str:
    return "".join(
        f'''<tr><th>{html.escape(label)}</th><td>{num(values["support"], 0)}</td>
        <td>{pct(values["precision"])}</td><td>{pct(values["recall"])}</td><td>{pct(values["f1"])}</td></tr>'''
        for label, values in per_class.items()
    )


def matrix_rows(matrix: dict[str, dict[str, int]]) -> str:
    labels = list(next(iter(matrix.values())).keys())
    header = "".join(f"<th>{html.escape(label)}</th>" for label in labels)
    rows = []
    for actual, values in matrix.items():
        cells = "".join(f"<td>{values[label]}</td>" for label in labels)
        rows.append(f"<tr><th>{html.escape(actual)}</th>{cells}</tr>")
    return f"<table class=matrix><thead><tr><th>Real \\ Predicha</th>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def generate(data: dict) -> str:
    evaluation = data["evaluation"]
    strict = data["classification"]
    recovered = data["recoverable_classification"]
    technical = data["technical"]
    recovery = data["recovery"]
    recovered_matrix = matrix_rows(recovered["confusion_matrix"])

    format_body = f'''<div class="metric-grid">
      <div><strong>{strict["valid_predictions"]}</strong><span>JSON estricto válido</span></div>
      <div><strong>{recovery["recovered"]}</strong><span>JSON recuperable</span></div>
      <div><strong>{strict["invalid_predictions"]}</strong><span>inválidos estrictos</span></div>
    </div><p>{recovery["fenced_json"]} respuestas llegaron dentro de un bloque Markdown. Se retiró únicamente ese envoltorio antes de calcular las métricas.</p>'''

    classification_body = f'''<div class="hero-metric"><strong>{pct(recovered["accuracy"])}</strong><span>accuracy</span></div>
      <div class="metric-line"><span>Macro-F1</span><b>{pct(recovered["macro_f1"])}</b></div>
      <div class="metric-line"><span>Casos correctos</span><b>{recovered["correct"]} de {evaluation["aligned_records"]}</b></div>'''

    class_body = f'''<table><thead><tr><th>Clase</th><th>Soporte</th><th>Precision</th><th>Recall</th><th>F1</th></tr></thead>
      <tbody>{table_rows(recovered["per_class"])}</tbody></table>'''

    performance_body = f'''<div class="metric-grid">
      <div><strong>{num(technical["latency_ms"]["mean"])} ms</strong><span>latencia media</span></div>
      <div><strong>{num(technical["latency_ms"]["p50"])} ms</strong><span>latencia P50</span></div>
      <div><strong>{num(technical["latency_ms"]["p95"])} ms</strong><span>latencia P95</span></div>
      <div><strong>{num(technical["ttft_ms"]["mean"])} ms</strong><span>TTFT media</span></div>
    </div><p>HTTP 200: {html.escape(str(technical["http_status_counts"].get("200", 0)))} de {evaluation["result_records"]}. Usage disponible en {technical["records_with_usage"]} registros.</p>'''

    return f'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Evaluación SLM · PQRS</title>
<style>
:root {{ --ink:#17202a; --muted:#66727f; --line:#dfe5ea; --paper:#f5f7f9; --card:#fff; --blue:#0057b8; --blue-soft:#eaf3ff; --amber:#a35b00; --amber-soft:#fff4df; --red:#a52b2b; --red-soft:#fff0f0; --green:#126b4f; --green-soft:#e9f7f1; }}
* {{ box-sizing:border-box }} body {{ margin:0; background:var(--paper); color:var(--ink); font-family:Inter,Segoe UI,Arial,sans-serif; line-height:1.5 }}
main {{ max-width:1180px; margin:auto; padding:42px 24px 72px }} header {{ display:flex; justify-content:space-between; gap:28px; align-items:flex-end; padding-bottom:30px; border-bottom:1px solid var(--line) }}
.kicker,.eyebrow {{ color:var(--blue); font-size:12px; font-weight:800; letter-spacing:.12em; text-transform:uppercase }} h1 {{ margin:8px 0 8px; font-size:clamp(32px,5vw,58px); line-height:1.02; letter-spacing:-.04em }} .lede {{ max-width:650px; color:var(--muted); font-size:17px; margin:0 }}
.meta {{ color:var(--muted); font-size:13px; text-align:right; white-space:nowrap }} .section-title {{ margin:42px 0 16px; font-size:14px; text-transform:uppercase; letter-spacing:.1em; color:var(--muted) }}
.grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px }} .card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:24px; box-shadow:0 8px 25px rgba(20,35,50,.04) }} .card h2 {{ margin:5px 0 18px; font-size:23px; letter-spacing:-.02em }} .card-body p {{ color:var(--muted); margin:14px 0 0 }}
.metric-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-top:8px }} .metric-grid.compact {{ grid-template-columns:repeat(4,1fr) }} .metric-grid div {{ background:#f7f9fb; border:1px solid #edf0f3; padding:13px; border-radius:10px }} .metric-grid strong,.hero-metric strong {{ display:block; font-size:25px; letter-spacing:-.04em }} .metric-grid span,.hero-metric span {{ display:block; color:var(--muted); font-size:12px }} .hero-metric {{ padding:12px 0 16px; border-bottom:1px solid var(--line); margin-bottom:8px }} .hero-metric strong {{ color:var(--blue); font-size:43px }} .metric-line {{ display:flex; justify-content:space-between; padding:6px 0; color:var(--muted) }} .metric-line b {{ color:var(--ink) }}
.conclusion {{ margin-top:20px; padding:14px 16px; border-radius:10px; background:var(--blue-soft); border-left:3px solid var(--blue) }} .conclusion span {{ color:var(--blue); font-size:11px; font-weight:800; letter-spacing:.1em; text-transform:uppercase }} .conclusion p {{ margin:4px 0 0; color:var(--ink); font-weight:600 }} .conclusion.warn {{ background:var(--amber-soft); border-color:var(--amber) }} .conclusion.warn span {{ color:var(--amber) }} .conclusion.alert {{ background:var(--red-soft); border-color:var(--red) }} .conclusion.alert span {{ color:var(--red) }} .conclusion.good {{ background:var(--green-soft); border-color:var(--green) }} .conclusion.good span {{ color:var(--green) }}
table {{ width:100%; border-collapse:collapse; font-size:14px }} th,td {{ padding:10px 8px; text-align:right; border-bottom:1px solid var(--line) }} th:first-child,td:first-child {{ text-align:left }} thead th {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.06em }} .matrix {{ font-size:12px }} .matrix th,.matrix td {{ padding:8px 6px }} code {{ font-family:Consolas,monospace; font-size:.9em }} .full {{ grid-column:1/-1 }} .notes {{ color:var(--muted); font-size:13px; margin-top:30px; padding-top:18px; border-top:1px solid var(--line) }}
@media(max-width:760px) {{ header {{ display:block }} .meta {{ text-align:left; margin-top:14px }} .grid {{ grid-template-columns:1fr }} .metric-grid,.metric-grid.compact {{ grid-template-columns:repeat(2,1fr) }} .full {{ grid-column:auto }} }}
@media print {{ body {{ background:#fff }} main {{ padding:20px }} .card {{ break-inside:avoid; box-shadow:none }} }}
</style></head><body><main>
<header><div><div class="kicker">Evaluación local · SLM</div><h1>PQRS: resultados y conclusiones</h1><p class="lede">Lectura ejecutiva de la clasificación generada por Qwen3-32B sobre 100 solicitudes.</p></div><div class="meta">Fuente: pqrs_classification_metrics.json<br>Datos textuales no incluidos</div></header>
<div class="section-title">01 · Formato de respuesta</div><section class="grid">
{card("Formato de respuesta", "Calidad técnica", format_body, "El modelo respondió técnicamente, pero no cumplió de forma consistente el contrato de JSON estricto. El formato debe medirse separado de la calidad de clasificación.", "warn")}
</section>
<div class="section-title">02 · Clasificación</div><section class="grid">
{card("Desempeño global", "Resultado principal", classification_body, "El modelo acierta 81 de 100 casos. La clasificación muestra una base útil, pero todavía requiere mejoras para distinguir de forma consistente las tres clases.", "neutral")}
{card("Desempeño por clase", "Detalle", class_body, "El modelo reconoce bien Reclamo, tiene desempeño intermedio en Petición y no identifica Queja en esta muestra. La clase Queja requiere revisión de ejemplos, etiquetas o instrucciones.", "alert")}
<div class="card full"><div class="eyebrow">Matriz de confusión</div><h2>Qué ocurrió entre las clases</h2>{recovered_matrix}{conclusion("Las 4 Quejas fueron clasificadas como Reclamo; además, 12 Peticiones fueron clasificadas como Reclamo. El principal patrón de error es sobrerrepresentar Reclamo.", "warn")}</div>
</section>
<div class="section-title">03 · Rendimiento del servicio</div><section class="grid">
{card("Latencia y operación", "Telemetría", performance_body, "La corrida fue estable a nivel de transporte: 100 respuestas HTTP 200. La latencia P95 es el indicador operativo que debe vigilarse en una siguiente comparación.", "good")}
</section>
<p class="notes">Nota metodológica: todas las métricas de calidad de clasificación de este reporte fueron calculadas sobre las respuestas recuperables. Para hacerlas utilizables, se retiró únicamente el envoltorio Markdown de 99 respuestas; no se modificó el JSONL original ni se enviaron nuevamente datos al modelo.</p>
</main></body></html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(generate(data), encoding="utf-8")
    print(f"HTML_GENERADO={args.output}")
    print(f"BYTES={args.output.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
