"""Anonimiza PII en una columna de un CSV o XLSX.

El script reemplaza por etiquetas los siguientes datos:
- correos electrónicos;
- teléfonos colombianos y teléfonos internacionales comunes;
- cédulas/documentos cuando aparecen con una etiqueta (CC, cédula, documento, etc.);
- nombres asociados a etiquetas de persona (nombre, titular, señor/a, me llamo, etc.).

Uso recomendado:
    python code/anonimizar_columna.py \
        --input datos.xlsx \
        --output datos_anonimizados.xlsx \
        --column "Nota"

Para CSV:
    python code/anonimizar_columna.py \
        --input datos.csv \
        --output datos_anonimizados.csv \
        --column "Nota"

El archivo original nunca se modifica. Primero se recomienda ejecutar --dry-run.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable


# Se dejan fuera nombres de proveedores/dominos: el correo completo se reemplaza primero.
EMAIL_RE = re.compile(
    r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)

# Incluye +57, espacios, guiones, paréntesis y números móviles colombianos.
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?\(?[2-9]\d{2}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"
)

# Cédulas/documentos con etiqueta. No se eliminan todos los números desnudos por defecto,
# porque podrían ser IDs de solicitudes, saldos, fechas o números de producto.
ID_RE = re.compile(
    r"(?i)\b(?:c[ée]dula|cc|documento(?:\s+de\s+identidad)?|identificaci[oó]n|nit)"
    r"\s*(?:n[°ºo.]?\s*)?(?:es|:|=|-)?\s*"
    r"(?:\d[\d.\- ]{4,}\d)\b"
)

# Nombres introducidos por expresiones frecuentes. Se exige al menos nombre y apellido
# para reducir falsos positivos en textos de PQRS.
NAME_RE = re.compile(
    r"(?ix)\b(?:"
    r"mi\s+nombre\s+es|me\s+llamo|nombre(?:\s+completo)?|"
    r"titular|se(?:ñ|n)or(?:a)?|sr(?:a)?\.??|apellidos?"
    r")\s*(?:es|:|=|-)?\s+"
    r"(?P<name>[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑa-záéíóúüñ'’-]+"
    r"(?:\s+[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑa-záéíóúüñ'’-]+){1,3})"
)

# También cubre patrones típicos en texto libre: "Juan Pérez, ..." o "Juan Pérez ...".
# Se usa solo con --aggressive-names, porque puede borrar palabras capitalizadas legítimas.
AGGRESSIVE_NAME_RE = re.compile(
    r"(?<![\wÁÉÍÓÚÜÑáéíóúüñ])"
    r"(?P<name>[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑa-záéíóúüñ'’-]+"
    r"\s+[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑa-záéíóúüñ'’-]+"
    r"(?:\s+[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑa-záéíóúüñ'’-]+)?)"
    r"(?![\wÁÉÍÓÚÜÑáéíóúüñ])"
)

# En modo agresivo se pueden cubrir documentos desnudos, con el riesgo de capturar IDs.
BARE_ID_RE = re.compile(r"(?<!\d)\d{6,10}(?!\d)")


Rule = tuple[str, re.Pattern[str], Callable[[re.Match[str]], str]]


def build_rules(aggressive_names: bool, aggressive_numbers: bool) -> list[Rule]:
    rules: list[Rule] = [
        ("correo", EMAIL_RE, lambda _m: "[CORREO_ELIMINADO]"),
        ("telefono", PHONE_RE, lambda _m: "[TELEFONO_ELIMINADO]"),
        ("cedula_documento", ID_RE, lambda m: re.sub(r"(?i)\b(c[ée]dula|cc|documento|identificaci[oó]n|nit)\b.*", lambda x: x.group(0), m.group(0))),
    ]

    # La función anterior conserva la etiqueta y reemplaza únicamente el valor numérico.
    rules[-1] = (
        "cedula_documento",
        ID_RE,
        lambda m: re.sub(r"\d[\d.\- ]{4,}\d\b", "[DOCUMENTO_ELIMINADO]", m.group(0)),
    )
    rules.append(("nombre_etiquetado", NAME_RE, lambda m: m.group(0)[: m.group(0).find(m.group("name"))] + "[NOMBRE_ELIMINADO]"))

    if aggressive_names:
        rules.append(("nombre_probable", AGGRESSIVE_NAME_RE, lambda _m: "[NOMBRE_ELIMINADO]"))
    if aggressive_numbers:
        rules.append(("numero_documento_sin_etiqueta", BARE_ID_RE, lambda _m: "[DOCUMENTO_ELIMINADO]"))
    return rules


def anonymize_text(text: object, rules: Iterable[Rule]) -> tuple[str, Counter[str]]:
    value = "" if text is None else str(text)
    counts: Counter[str] = Counter()
    for label, pattern, replacement in rules:
        value, number = pattern.subn(replacement, value)
        counts[label] += number
    return value, counts


def detect_csv_format(path: Path) -> tuple[str, str, bool]:
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    encoding = "utf-8-sig" if has_bom else "utf-8"
    sample = raw[:200_000].decode(encoding, errors="replace")
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    return encoding, delimiter, has_bom


def process_csv(input_path: Path, output_path: Path, column: str, rules: list[Rule], dry_run: bool) -> Counter[str]:
    encoding, delimiter, _has_bom = detect_csv_format(input_path)
    counts: Counter[str] = Counter()
    rows = 0

    with input_path.open("r", encoding=encoding, newline="") as source:
        reader = csv.DictReader(source, delimiter=delimiter)
        if reader.fieldnames is None:
            raise ValueError("El CSV no tiene encabezado.")
        if column not in reader.fieldnames:
            raise ValueError(f"No existe la columna {column!r}. Columnas: {reader.fieldnames}")

        if dry_run:
            for row in reader:
                _, row_counts = anonymize_text(row.get(column), rules)
                counts.update(row_counts)
                rows += 1
            counts["filas"] = rows
            return counts

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8-sig" if encoding == "utf-8-sig" else "utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=reader.fieldnames, delimiter=delimiter, extrasaction="ignore")
            writer.writeheader()
            for row in reader:
                row[column], row_counts = anonymize_text(row.get(column), rules)
                counts.update(row_counts)
                writer.writerow(row)
                rows += 1

    counts["filas"] = rows
    return counts


def process_xlsx(input_path: Path, output_path: Path, column: str, rules: list[Rule], dry_run: bool, sheet: str | None) -> Counter[str]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("Para XLSX necesitas instalar openpyxl en tu entorno local.") from exc

    workbook = load_workbook(input_path)
    worksheet = workbook[sheet] if sheet else workbook.active
    headers = [cell.value for cell in worksheet[1]]
    if column not in headers:
        raise ValueError(f"No existe la columna {column!r} en la hoja {worksheet.title!r}. Columnas: {headers}")
    column_index = headers.index(column) + 1
    counts: Counter[str] = Counter()
    rows = 0

    for row in worksheet.iter_rows(min_row=2, min_col=column_index, max_col=column_index):
        cell = row[0]
        new_value, row_counts = anonymize_text(cell.value, rules)
        counts.update(row_counts)
        if not dry_run:
            cell.value = new_value
        rows += 1

    counts["filas"] = rows
    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(output_path)
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Anonimiza PII en una columna de CSV o XLSX.")
    parser.add_argument("--input", required=True, type=Path, help="Archivo CSV o XLSX original.")
    parser.add_argument("--output", required=True, type=Path, help="Archivo nuevo de salida; nunca sobrescribe el original.")
    parser.add_argument("--column", required=True, help="Nombre exacto de la columna que contiene el texto.")
    parser.add_argument("--sheet", help="Hoja XLSX. Por defecto se usa la hoja activa.")
    parser.add_argument("--dry-run", action="store_true", help="Solo cuenta coincidencias; no crea el archivo de salida.")
    parser.add_argument("--aggressive-names", action="store_true", help="También reemplaza pares de palabras capitalizadas que parecen nombres.")
    parser.add_argument("--aggressive-numbers", action="store_true", help="También reemplaza números desnudos de 6 a 10 dígitos; puede capturar IDs o números de producto.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = args.input.resolve()
    output_path = args.output.resolve()

    if not input_path.exists():
        print(f"ERROR: no existe el archivo de entrada: {input_path}", file=sys.stderr)
        return 2
    if input_path == output_path:
        print("ERROR: la salida debe ser distinta del archivo original.", file=sys.stderr)
        return 2

    suffix = input_path.suffix.lower()
    if suffix not in {".csv", ".xlsx"}:
        print("ERROR: solo se soportan archivos .csv y .xlsx.", file=sys.stderr)
        return 2

    rules = build_rules(args.aggressive_names, args.aggressive_numbers)
    try:
        if suffix == ".csv":
            counts = process_csv(input_path, output_path, args.column, rules, args.dry_run)
        else:
            counts = process_xlsx(input_path, output_path, args.column, rules, args.dry_run, args.sheet)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    action = "Simulación completada" if args.dry_run else f"Archivo creado: {output_path}"
    print(action)
    print(f"Filas procesadas: {counts.pop('filas', 0)}")
    print("Coincidencias reemplazadas:")
    for label, count in sorted(counts.items()):
        print(f"  {label}: {count}")
    if not args.aggressive_names:
        print("Aviso: nombres sin una etiqueta explícita pueden no detectarse; revise los datos anonimizados.")
    if not args.aggressive_numbers:
        print("Aviso: números de documento sin etiqueta no se reemplazan por defecto para evitar borrar IDs o números de producto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
