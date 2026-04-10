from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .dxf_text_copy import copy_text_entities
from .service import generate_report_file


def _add_report_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("drawing", help="Путь к DWG или DXF файлу")
    parser.add_argument("--note", help="Путь к пояснительной записке (TXT/RST/MD/DOCX)")
    parser.add_argument(
        "--output",
        default="reports/result.xlsx",
        help="Куда сохранить итоговый Excel-файл",
    )


def _build_legacy_report_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parsedwg",
        description="Извлечение позиций из DWG/DXF и формирование СО, ВОР и сметы.",
    )
    _add_report_arguments(parser)
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parsedwg",
        description="Работа с DWG/DXF: отчёты и фильтрация текстовых сущностей.",
    )
    subparsers = parser.add_subparsers(dest="command")

    report_parser = subparsers.add_parser(
        "report",
        help="Сформировать Excel-отчёт из DWG/DXF и записки.",
    )
    _add_report_arguments(report_parser)

    copy_parser = subparsers.add_parser(
        "copy-text",
        help="Скопировать из DXF только сущности TEXT и MTEXT.",
    )
    copy_parser.add_argument("source", help="Исходный DXF-файл")
    copy_parser.add_argument("target", help="Куда сохранить отфильтрованный DXF-файл")
    copy_parser.add_argument(
        "--modelspace-only",
        action="store_true",
        help="Копировать только текст из modelspace, без paper space layout'ов.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] not in {"report", "copy-text"}:
        args = _build_legacy_report_parser().parse_args(argv)
        output_path = generate_report_file(args.drawing, args.note, Path(args.output))
        print(f"Готово: {output_path}")
        return 0

    args = build_parser().parse_args(argv)
    if args.command == "report":
        output_path = generate_report_file(args.drawing, args.note, Path(args.output))
        print(f"Готово: {output_path}")
        return 0

    copied_count = copy_text_entities(
        args.source,
        args.target,
        modelspace_only=args.modelspace_only,
    )
    print(f"Скопировано текстовых сущностей: {copied_count}")
    print(f"Результат сохранён в: {Path(args.target)}")
    return 0
