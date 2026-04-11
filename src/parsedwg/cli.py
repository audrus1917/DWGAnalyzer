"""Консольная точка входа для работы с DWG/DXF."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from .explorer import DXFExplorer

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

type ResultRow = dict[str, object]

SUPPORTED_DRAWING_SUFFIXES = {".dxf", ".dwg"}


def _iter_drawing_files(path: Path) -> list[Path]:
    """Возвращает один файл или все подходящие файлы каталога рекурсивно."""

    if not path.exists():
        raise FileNotFoundError(f"Путь {path} не найден.")

    if path.is_file():
        return [path]

    drawing_files = sorted(
        file_path
        for file_path in path.rglob("*")
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_DRAWING_SUFFIXES
    )
    if not drawing_files:
        raise ValueError(f"В каталоге {path} не найдено файлов DWG/DXF.")
    return drawing_files


def _save_rows_to_json(output_path: Path, rows: list[ResultRow]) -> None:
    """Сохраняет строки результата в JSON-файл."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _format_rows_as_table(rows: list[ResultRow]) -> str:
    """Форматирует строки результата в простую ASCII-таблицу."""

    if not rows:
        return "Нет данных."

    columns = list(rows[0].keys())
    prepared_rows = [[str(row.get(column, "")) for column in columns] for row in rows]
    widths = {
        column: max(len(column), *(len(values[index]) for values in prepared_rows))
        for index, column in enumerate(columns)
    }

    header = " | ".join(column.ljust(widths[column]) for column in columns)
    separator = "-+-".join("-" * widths[column] for column in columns)
    body = [
        " | ".join(values[index].ljust(widths[column]) for index, column in enumerate(columns))
        for values in prepared_rows
    ]
    return "\n".join([header, separator, *body])


def _print_rows_table(rows: list[ResultRow]) -> None:
    """Выводит строки результата на экран в виде таблицы."""

    print(_format_rows_as_table(rows))


def _resolve_output_path(source_root: Path, drawing_path: Path, output_path: Path) -> Path:
    """Определяет путь выходного JSON-файла для одного обработанного файла."""

    if source_root.is_file():
        return output_path

    relative_path = drawing_path.relative_to(source_root).with_suffix(".json")
    return output_path / relative_path


def _handle_list_command(
    source_path: Path,
    output_path: Path | None,
    collector: Callable[[DXFExplorer], list[ResultRow]],
) -> int:
    """Выполняет list-команду для одного файла или каталога файлов."""

    drawing_files = _iter_drawing_files(source_path)
    if output_path is not None and source_path.is_dir():
        output_path.mkdir(parents=True, exist_ok=True)

    all_rows: list[ResultRow] = []
    for drawing_file in drawing_files:
        explorer = DXFExplorer(drawing_file)
        rows = collector(explorer)

        if output_path is None:
            all_rows.extend(rows)
            continue

        target_path = _resolve_output_path(source_path, drawing_file, output_path)
        _save_rows_to_json(target_path, rows)
        logger.info("JSON сохранён: %s", target_path)

    if output_path is None:
        _print_rows_table(all_rows)

    return 0


def main(argv: list[str] | None = None) -> int:
    """Точка входа для командной строки."""

    argv = list(sys.argv[1:] if argv is None else argv)

    list_common = argparse.ArgumentParser(add_help=False)
    list_common.add_argument("path", help="Путь к DWG/DXF файлу или каталогу")
    list_common.add_argument(
        "-o",
        "--output",
        help="Путь к JSON-файлу для одного входного файла или каталогу для пакетной обработки.",
    )

    extract_common = argparse.ArgumentParser(add_help=False)
    extract_common.add_argument("drawing", help="Путь к DWG или DXF файлу")

    parser = argparse.ArgumentParser(
        prog="parsedwg",
        description="Работа с DWG/DXF: получение данных и выполнение операций",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "list-layouts",
        parents=[list_common],
        help="Показать доступные layout'ы в DWG/DXF файле или каталоге.",
    )
    subparsers.add_parser(
        "list-blocks",
        parents=[list_common],
        help="Показать доступные блоки в DWG/DXF файле или каталоге.",
    )
    extract_block_parser = subparsers.add_parser(
        "extract-block",
        parents=[extract_common],
        help="Извлечь блок в отдельные файл.",
    )
    extract_block_parser.add_argument("block_name", help="Имя блока для извлечения")

    args = parser.parse_args(argv)

    if args.command == "list-layouts":
        output_path = Path(args.output) if args.output else None
        return _handle_list_command(
            Path(args.path),
            output_path,
            lambda explorer: explorer.list_layouts(),
        )

    if args.command == "list-blocks":
        output_path = Path(args.output) if args.output else None
        return _handle_list_command(
            Path(args.path),
            output_path,
            lambda explorer: explorer.list_blocks(),
        )

    explorer = DXFExplorer(args.drawing)
    if args.command == "extract-block":
        explorer.extract_block(args.block_name)

    return 0


__all__ = ["DXFExplorer", "main"]
