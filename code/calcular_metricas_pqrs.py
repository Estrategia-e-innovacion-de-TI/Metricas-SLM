#!/usr/bin/env python3
"""Calcula métricas locales de clasificación para la evaluación PQRS.

No envía datos a ningún servicio. Lee la etiqueta real desde el XLSX local y
la predicción desde el JSONL generado por la corrida del modelo. No copia ni
escribe los textos de Nota, Resumen o raw_output en los reportes.

Uso:
    python calcular_metricas_pqrs.py
    python calcular_metricas_pqrs.py --self-test
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


LABELS = ("Queja", "Petición", "Reclamo")
INVALID = "INVALIDA"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = ROOT / "data" / "pqrs_anonimizado.xlsx"
DEFAULT_RESULTS = ROOT / "resultados" / "pqrs_gateway_results.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "metricas"


def load_reference(path: Path) -> dict[str, str]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        worksheet = workbook.active
        rows = worksheet.iter_rows(values_only=True)
        headers = list(next(rows))
        required = ("Número de la solicitud", "Clasificación")
        missing = [column for column in required if column not in headers]
        if missing:
            raise ValueError(f"Faltan columnas de referencia: {', '.join(missing)}")
        id_index = headers.index("Número de la solicitud")
        label_index = headers.index("Clasificación")
        reference: dict[str, str] = {}
        for row_number, row in enumerate(rows, 2):
            case_id = str(row[id_index]).strip() if row[id_index] is not None else ""
            label = str(row[label_index]).strip() if row[label_index] is not None else ""
            if not case_id or not label:
                raise ValueError(f"Referencia incompleta en fila {row_number}")
            if case_id in reference:
                raise ValueError(f"ID duplicado en referencia: fila {row_number}")
            reference[case_id] = label
        return reference
    finally:
        workbook.close()


def load_predictions(path: Path) -> dict[str, dict[str, Any]]:
    predictions: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            case_id = str(record.get("id", "")).strip()
            if not case_id:
                raise ValueError(f"Resultado sin id en línea {line_number}")
            if case_id in predictions:
                raise ValueError(f"ID duplicado en resultados: línea {line_number}")
            predictions[case_id] = record
    return predictions


def recover_fenced_predictions(predictions: dict[str, dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    """Recupera solo JSON envuelto en un bloque Markdown ```...```.

    Esto se reporta separado de la métrica estricta: retirar el envoltorio no
    cambia el resultado original ni oculta un incumplimiento de formato.
    """
    recovered = {case_id: dict(record) for case_id, record in predictions.items()}
    counts = {"fenced_json": 0, "recovered": 0, "not_recoverable": 0}
    for record in recovered.values():
        raw_output = record.get("raw_output")
        if not isinstance(raw_output, str):
            counts["not_recoverable"] += 1
            continue
        text = raw_output.strip()
        if not (text.startswith("```") and text.endswith("```")):
            counts["not_recoverable"] += 1
            continue
        counts["fenced_json"] += 1
        body = text.split("\n", 1)[1] if "\n" in text else ""
        body = body.rsplit("```", 1)[0].strip()
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            counts["not_recoverable"] += 1
            continue
        if isinstance(parsed, dict):
            record["classification"] = parsed.get("classification")
            counts["recovered"] += 1
        else:
            counts["not_recoverable"] += 1
    return recovered, counts


def safe_division(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def calculate_metrics(reference: dict[str, str], predictions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    reference_ids = set(reference)
    prediction_ids = set(predictions)
    missing_results = sorted(reference_ids - prediction_ids)
    unexpected_results = sorted(prediction_ids - reference_ids)
    aligned_ids = sorted(reference_ids & prediction_ids)

    invalid_reference = sorted({label for label in reference.values()} - set(LABELS))
    if invalid_reference:
        raise ValueError("Etiquetas de referencia no permitidas: " + ", ".join(invalid_reference))

    confusion_labels = list(LABELS) + [INVALID]
    confusion = {actual: {predicted: 0 for predicted in confusion_labels} for actual in confusion_labels}
    error_counts: Counter[str] = Counter()
    valid_predictions = 0
    correct = 0
    invalid_predictions = 0
    latencies: list[float] = []
    ttfts: list[float] = []
    http_statuses: Counter[str] = Counter()
    usages_present = 0
    detail_rows: list[dict[str, Any]] = []

    for case_id in aligned_ids:
        actual = reference[case_id]
        record = predictions[case_id]
        raw_prediction = record.get("classification")
        predicted = str(raw_prediction).strip() if raw_prediction is not None else ""
        predicted_label = predicted if predicted in LABELS else INVALID
        if predicted_label == INVALID:
            invalid_predictions += 1
            error_counts["prediccion_invalida_o_ausente"] += 1
        else:
            valid_predictions += 1
        if predicted_label == actual:
            correct += 1
        confusion[actual][predicted_label] += 1

        if isinstance(record.get("latency_ms"), (int, float)):
            latencies.append(float(record["latency_ms"]))
        if isinstance(record.get("ttft_ms"), (int, float)):
            ttfts.append(float(record["ttft_ms"]))
        if record.get("http_status") is not None:
            http_statuses[str(record["http_status"])] += 1
        if isinstance(record.get("usage"), dict) and record["usage"]:
            usages_present += 1

        detail_rows.append({
            "id": case_id,
            "actual": actual,
            "predicted": predicted_label,
            "correct": predicted_label == actual,
            "valid_prediction": predicted_label != INVALID,
        })

    total = len(aligned_ids)
    per_class: dict[str, dict[str, float | int]] = {}
    f1_values: list[float] = []
    for label in LABELS:
        tp = confusion[label][label]
        fp = sum(confusion[actual][label] for actual in confusion_labels if actual != label)
        fn = sum(confusion[label][predicted] for predicted in confusion_labels if predicted != label)
        precision = safe_division(tp, tp + fp)
        recall = safe_division(tp, tp + fn)
        f1 = safe_division(2 * precision * recall, precision + recall)
        f1_values.append(f1)
        per_class[label] = {
            "support": sum(confusion[label].values()),
            "true_positive": tp,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }

    def summary(values: list[float]) -> dict[str, float | int | None]:
        if not values:
            return {"count": 0, "mean": None, "p50": None, "p95": None}
        ordered = sorted(values)
        def percentile(percent: float) -> float:
            position = (len(ordered) - 1) * percent
            lower = math.floor(position)
            upper = math.ceil(position)
            if lower == upper:
                return ordered[lower]
            return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
        return {
            "count": len(values),
            "mean": sum(values) / len(values),
            "p50": percentile(0.50),
            "p95": percentile(0.95),
        }

    return {
        "evaluation": {
            "reference_records": len(reference),
            "result_records": len(predictions),
            "aligned_records": total,
            "missing_result_records": len(missing_results),
            "unexpected_result_records": len(unexpected_results),
            "missing_result_ids": missing_results,
            "unexpected_result_ids": unexpected_results,
        },
        "labels": list(LABELS),
        "classification": {
            "accuracy": safe_division(correct, total),
            "correct": correct,
            "incorrect": total - correct,
            "valid_predictions": valid_predictions,
            "invalid_predictions": invalid_predictions,
            "macro_f1": sum(f1_values) / len(f1_values),
            "per_class": per_class,
            "confusion_matrix": confusion,
        },
        "technical": {
            "latency_ms": summary(latencies),
            "ttft_ms": summary(ttfts),
            "http_status_counts": dict(http_statuses),
            "records_with_usage": usages_present,
            "records_with_error_field": sum(1 for case_id in aligned_ids if predictions[case_id].get("error")),
        },
        "detail_file_contains_only": ["id", "actual", "predicted", "correct", "valid_prediction"],
        "detail": detail_rows,
    }


def write_outputs(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "pqrs_classification_metrics.json"
    csv_path = output_dir / "pqrs_classification_detail.csv"
    report_to_write = dict(report)
    detail = report_to_write.pop("detail")
    json_path.write_text(json.dumps(report_to_write, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "actual", "predicted", "correct", "valid_prediction"])
        writer.writeheader()
        writer.writerows(detail)
    return json_path, csv_path


def run_self_test() -> None:
    reference = {"1": "Queja", "2": "Petición", "3": "Reclamo", "4": "Reclamo"}
    predictions = {
        "1": {"classification": "Queja"},
        "2": {"classification": "Petición"},
        "3": {"classification": "Queja"},
        "4": {"classification": "No válida"},
    }
    report = calculate_metrics(reference, predictions)
    classification = report["classification"]
    assert classification["correct"] == 2
    assert classification["incorrect"] == 2
    assert classification["invalid_predictions"] == 1
    assert classification["confusion_matrix"]["Reclamo"]["Queja"] == 1
    assert classification["confusion_matrix"]["Reclamo"][INVALID] == 1
    print("SELF_TEST_PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        return 0

    reference = load_reference(args.reference)
    predictions = load_predictions(args.results)
    strict_report = calculate_metrics(reference, predictions)
    recovered_predictions, recovery_counts = recover_fenced_predictions(predictions)
    recovered_report = calculate_metrics(reference, recovered_predictions)
    strict_report["recoverable_classification"] = recovered_report["classification"]
    strict_report["recovery"] = recovery_counts
    json_path, csv_path = write_outputs(strict_report, args.output_dir)
    classification = strict_report["classification"]
    recoverable = strict_report["recoverable_classification"]
    print(f"METRICAS_JSON={json_path}")
    print(f"DETALLE_CSV={csv_path}")
    print(f"REFERENCE_RECORDS={strict_report['evaluation']['reference_records']}")
    print(f"RESULT_RECORDS={strict_report['evaluation']['result_records']}")
    print(f"ALIGNED_RECORDS={strict_report['evaluation']['aligned_records']}")
    print(f"ACCURACY={classification['accuracy']:.6f}")
    print(f"MACRO_F1={classification['macro_f1']:.6f}")
    print(f"INVALID_PREDICTIONS={classification['invalid_predictions']}")
    print(f"RECOVERABLE_ACCURACY={recoverable['accuracy']:.6f}")
    print(f"RECOVERABLE_MACRO_F1={recoverable['macro_f1']:.6f}")
    print(f"RECOVERED_RECORDS={recovery_counts['recovered']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
