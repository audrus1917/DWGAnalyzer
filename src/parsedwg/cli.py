"""Консольная точка входа для работы с DWG/DXF."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from collections.abc import Callable
from pathlib import Path

from .explorer import DXFExplorer
from .dwg_tree_ingest import run_dwg_tree_ingest
from .docs_ingest import run_documents_ingest
from .name_tags import collect_name_tags

type ResultRow = dict[str, object]


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.getLogger("ezdxf").disabled = True
logger = logging.getLogger(__name__)


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


def _handle_search_command(
    query: str,
    entity_type: str | None,
    limit: int,
    output_path: Path | None,
    parent_id: str | None = None,
) -> int:
    """Полнотекстовый поиск по БД PostgreSQL (таблица entity)."""
    from .db import search_entities

    rows: list[ResultRow] = asyncio.run(search_entities(query, entity_type, limit, parent_id))

    if not rows:
        print("Нет результатов.")
        return 0

    if output_path is not None:
        _save_rows_to_json(output_path, rows)
        logger.info("JSON сохранён: %s", output_path)
        return 0

    _print_rows_table(rows)
    return 0


def _handle_index_command(
    entity_type: str | None,
    batch_size: int,
    reindex: bool,
) -> int:
    """Генерирует и сохраняет эмбеддинги для сущностей в БД."""
    from .rag import index_entities

    count = asyncio.run(index_entities(entity_type, batch_size, reindex))
    print(f"Проиндексировано: {count}")
    return 0


def _handle_ask_command(
    question: str,
    entity_type: str | None,
    top_k: int,
    output_path: Path | None,
) -> int:
    """RAG-запрос: векторный поиск + генерация ответа через llama."""
    from .rag import ask

    result: ResultRow = asyncio.run(ask(question, entity_type, top_k))

    if output_path is not None:
        _save_rows_to_json(output_path, [result])
        logger.info("JSON сохранён: %s", output_path)
        return 0

    print(result["answer"])
    print()
    print("Источники:")
    _print_rows_table(result["sources"])  # type: ignore[arg-type]
    return 0


def _handle_extract_name_tags_command(source_path: Path, output_path: Path | None) -> int:
    """Извлекает смысловые теги из имен файлов для файла или каталога."""

    rows = collect_name_tags(source_path)
    if output_path is None:
        _print_rows_table(rows)
        return 0

    _save_rows_to_json(output_path, rows)
    logger.info("JSON сохранён: %s", output_path)
    return 0


def handle_ingest_dwg_tree_command(source_path: Path, workers: int) -> int:
    """Сканирует DWG/ZIP, конвертирует в DXF и сохраняет дерево в БД."""

    summary = run_dwg_tree_ingest(source_path, conversion_workers=workers)
    print(f"Найдено DWG: {summary['dwg_count']}")
    print(f"Сконвертировано DXF: {summary['dxf_count']}")
    print(f"Создано сущностей в БД: {summary['created_entities']}")
    print(summary)
    # print(f"Список источников DWG: {summary['source_list']}")
    # print(f"Список сконвертированных DXF: {summary['converted_list']}")
    return 0


def _handle_ingest_docs_command(source_path: Path) -> int:
    """Рекурсивно индексирует PDF/DOCX/XLSX/CSV документы в таблицу entity."""

    summary = run_documents_ingest(source_path)
    print(f"Найдено документов: {summary['doc_count']}")
    print(f"Создано сущностей в БД: {summary['created_entities']}")
    print(f"Источник: {summary['source']}")
    return 0


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
    extract_name_tags_parser = subparsers.add_parser(
        "extract-name-tags",
        help="Извлечь смысловые теги из имен файлов (рекурсивно для каталога).",
    )
    extract_name_tags_parser.add_argument("path", help="Путь к файлу или каталогу")
    extract_name_tags_parser.add_argument(
        "-o",
        "--output",
        help="Путь к JSON-файлу с результатами.",
    )

    ingest_dwg_tree_parser = subparsers.add_parser(
        "ingest-dwg-tree",
        help=(
            "Рекурсивно найти DWG (включая ZIP), сконвертировать в DXF в пуле процессов "
            "и загрузить дерево блоков/layers в БД."
        ),
    )
    ingest_dwg_tree_parser.add_argument(
        "path",
        help="Путь к каталогу для рекурсивного обхода.",
    )
    ingest_dwg_tree_parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help=(
            "Количество процессов для этапа конвертации DWG в DXF "
            "(<=0: авторасчет по CPU)."
        ),
    )

    ingest_docs_parser = subparsers.add_parser(
        "ingest-docs",
        help="Рекурсивно найти PDF/DOCX/XLSX/CSV и загрузить в БД для RAG.",
    )
    ingest_docs_parser.add_argument(
        "path",
        help="Путь к файлу или каталогу для рекурсивного обхода.",
    )

    search_parser = subparsers.add_parser(
        "search",
        help="Полнотекстовый поиск сущностей в БД PostgreSQL.",
    )
    search_parser.add_argument("query", help="Поисковый запрос.")
    search_parser.add_argument(
        "--type",
        dest="type",
        choices=["folder", "file", "zipfile", "zipped_file", "block", "layout", "layer", "primitive"],
        help="Фильтр по типу сущности.",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Максимальное число результатов (по умолчанию: 20).",
    )
    search_parser.add_argument(
        "--parent-id",
        dest="parent_id",
        default=None,
        help="Фильтр по parent_id: вернуть только прямых потомков этого UUID.",
    )
    search_parser.add_argument(
        "-o",
        "--output",
        help="Путь к JSON-файлу для сохранения результатов.",
    )

    _entity_type_choices = [
        "folder", "file", "zipfile", "zipped_file", "block", "layout", "layer", "primitive"
    ]

    index_parser = subparsers.add_parser(
        "index",
        help="Создать/обновить эмбеддинги для сущностей в БД (nomic-embed-text).",
    )
    index_parser.add_argument(
        "--type",
        dest="type",
        choices=_entity_type_choices,
        help="Индексировать только указанный тип сущностей.",
    )
    index_parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        dest="batch_size",
        help="Размер батча запросов к Ollama (по умолчанию: 50).",
    )
    index_parser.add_argument(
        "--reindex",
        action="store_true",
        help="Пересоздать эмбеддинги, даже если они уже есть.",
    )

    ask_parser = subparsers.add_parser(
        "ask",
        help="RAG-запрос: векторный поиск + генерация ответа через llama3.2.",
    )
    ask_parser.add_argument("question", help="Вопрос на естественном языке.")
    ask_parser.add_argument(
        "--type",
        dest="type",
        choices=_entity_type_choices,
        help="Фильтр по типу сущности.",
    )
    ask_parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        dest="top_k",
        help="Число ближайших источников для контекста (по умолчанию: 5).",
    )
    ask_parser.add_argument(
        "-o",
        "--output",
        help="Путь к JSON-файлу для сохранения ответа и источников.",
    )

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

    if args.command == "extract-name-tags":
        output_path = Path(args.output) if args.output else None
        return _handle_extract_name_tags_command(Path(args.path), output_path)

    if args.command == "ingest-dwg-tree":
        return handle_ingest_dwg_tree_command(Path(args.path), workers=max(1, args.workers))

    if args.command == "ingest-docs":
        return _handle_ingest_docs_command(Path(args.path))

    if args.command == "search":
        output_path = Path(args.output) if args.output else None
        return _handle_search_command(
            query=args.query,
            entity_type=args.type,
            limit=args.limit,
            output_path=output_path,
            parent_id=args.parent_id,
        )

    if args.command == "index":
        return _handle_index_command(
            entity_type=args.type,
            batch_size=args.batch_size,
            reindex=args.reindex,
        )

    if args.command == "ask":
        output_path = Path(args.output) if args.output else None
        return _handle_ask_command(
            question=args.question,
            entity_type=args.type,
            top_k=args.top_k,
            output_path=output_path,
        )

    explorer = DXFExplorer(args.drawing)
    if args.command == "extract-block":
        explorer.extract_block(args.block_name)

    return 0


__all__ = ["DXFExplorer", "main"]
