from __future__ import annotations

import argparse
from pathlib import Path

from .service import generate_report_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parsedwg",
        description="Извлечение позиций из DWG/DXF и формирование СО, ВОР и сметы.",
    )
    parser.add_argument("drawing", help="Путь к DWG или DXF файлу")
    parser.add_argument("--note", help="Путь к пояснительной записке (TXT/RST/MD/DOCX)")
    parser.add_argument(
        "--output",
        default="reports/result.xlsx",
        help="Куда сохранить итоговый Excel-файл",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_path = generate_report_file(args.drawing, args.note, Path(args.output))
    print(f"Готово: {output_path}")
    return 0
