"""Консольная точка входа для работы с DWG/DXF."""

from __future__ import annotations

import asyncio
import json
import logging
import sys

from collections.abc import Callable
from pathlib import Path

from . import constants
from .explorer import DXFExplorer
from .process_tree import run_process_tree
from .docs_ingest import run_documents_ingest
from .utils import build_args_parser



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


def handle_search_command(
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
        return constants.OK

    if output_path is not None:
        _save_rows_to_json(output_path, rows)
        logger.info("JSON сохранён: %s", output_path)
        return constants.OK

    _print_rows_table(rows)
    return constants.OK


def handle_index_command(
    entity_type: str | None,
    batch_size: int,
    reindex: bool,
) -> int:
    """Генерирует и сохраняет эмбеддинги для сущностей в БД."""
    from .rag import index_entities

    count = asyncio.run(index_entities(entity_type, batch_size, reindex))
    print(f"Проиндексировано: {count}")
    return constants.OK


def handle_ask_command(
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
        return constants.OK

    print(result["answer"])
    print()
    print("Источники:")
    _print_rows_table(result["sources"])  # type: ignore[arg-type]
    return constants.OK


def handle_process_command(
    source_path: Path,
    workers: int,
    project_name: str | None = None,
    project_description: str | None = None,
    created_by: str | None = None,
    ai_name_tags: bool = False,
    ai_model: str = "llama3.1:8b",
    ai_base_url: str = "http://localhost:11434/v1",
    ai_api_key: str = "ollama",
) -> int:
    """Сканирует DWG/DXF, сохраняет дерево сущностей в БД и привязывает к проекту."""

    try:
        name_tags_config = _build_name_tags_config(
            enabled=ai_name_tags,
            model=ai_model,
            base_url=ai_base_url,
            api_key=ai_api_key,
        )
        summary = run_process_tree(
            source_path,
            conversion_workers=workers,
            project_name=project_name,
            project_description=project_description,
            created_by=created_by,
            name_tags_config=name_tags_config,
        )
        print(f"Создан проект: {summary['project_id']}")
        print(f"Найдено файлов: {summary['file_count']}")
        print(f"Обработано файлов: {summary['processed_count']}")
        print(f"Создано сущностей в БД: {summary['created_entities']}")
        return constants.OK
    except ValueError as e:
        logger.error("Ошибка при обработке каталога / файла: %s", e)
        return constants.ERROR
    except RuntimeError as e:
        logger.error("Ошибка AI-режима: %s", e)
        return constants.ERROR


def _build_name_tags_config(
    enabled: bool,
    model: str,
    base_url: str,
    api_key: str,
):
    if not enabled:
        return None

    from .langchain_name_tags import ensure_langchain_available

    ensure_langchain_available()
    return {
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
    }


def handle_process_docs_command(source_path: Path) -> int:
    """Рекурсивно индексирует PDF/DOCX/XLSX/CSV документы в таблицу entity."""

    summary = run_documents_ingest(source_path)
    print(f"Найдено документов: {summary['doc_count']}")
    print(f"Создано сущностей в БД: {summary['created_entities']}")
    print(f"Источник: {summary['source']}")
    return constants.OK


def handle_extract_name_tags_command(
    source_path: Path,
    output_path: Path | None,
    ai_name_tags: bool = False,
    ai_model: str = "llama3.1:8b",
    ai_base_url: str = "http://localhost:11434/v1",
    ai_api_key: str = "ollama",
) -> int:
    """Извлекает смысловые теги из имен файлов/каталогов."""
    from .name_tags import collect_name_tags

    try:
        ai_extractor = None
        if ai_name_tags:
            from .langchain_name_tags import LangChainAgentConfig, LangChainNameTagsExtractor

            ensure_config = _build_name_tags_config(
                enabled=True,
                model=ai_model,
                base_url=ai_base_url,
                api_key=ai_api_key,
            )
            assert ensure_config is not None
            ai_extractor = LangChainNameTagsExtractor.from_config(
                LangChainAgentConfig(
                    model=ensure_config["model"],
                    base_url=ensure_config["base_url"],
                    api_key=ensure_config["api_key"],
                )
            )

        rows = collect_name_tags(source_path, ai_extractor=ai_extractor)

        if output_path is not None:
            _save_rows_to_json(output_path, rows)
            logger.info("JSON сохранён: %s", output_path)
            return constants.OK

        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return constants.OK
    except RuntimeError as e:
        logger.error("Ошибка AI-режима: %s", e)
        return constants.ERROR
    except Exception as e:
        logger.error("Сбой AI-экстракции: %s", e)
        return constants.UNBOUND_ERROR


def handle_project_add_command(
    name: str,
    description: str | None,
    created_by: str | None,
) -> int:
    """Создаёт проект."""
    from .db import create_project

    project = asyncio.run(create_project(name=name, description=description, created_by=created_by))
    print(f"Проект создан: {project['id']}")
    print(f"Название: {project['name']}")
    return constants.OK


def handle_project_update_command(
    project_id: str,
    name: str | None,
    description: str | None,
    created_by: str | None,
) -> int:
    """Обновляет проект."""
    from .db import update_project

    project = asyncio.run(
        update_project(
            project_id=project_id,
            name=name,
            description=description,
            created_by=created_by,
        )
    )
    if project is None:
        print("Проект не найден.")
        return constants.NOT_FOUND

    print(f"Проект обновлён: {project['id']}")
    print(f"Название: {project['name']}")
    return constants.OK


def handle_project_delete_command(project_id: str, yes: bool) -> int:
    """Удаляет проект с подтверждением согласия."""
    from .db import delete_project

    if not yes:
        answer = input(
            f"Удалить проект {project_id}? Введите YES для подтверждения: "
        ).strip()
        if answer != "YES":
            print("Удаление отменено.")
            return constants.ERROR

    deleted = asyncio.run(delete_project(project_id=project_id))
    if not deleted:
        print("Проект не найден.")
        return constants.NOT_FOUND

    print(f"Проект удалён: {project_id}")
    return constants.OK


def handle_list_command(
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

    return constants.OK


def main(argv: list[str] | None = None) -> int:
    """Точка входа для командной строки."""

    parser = build_args_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(argv)

    return_code: int = 0
    match args.command:

        case "list-layouts":
            output_path = Path(args.output) if args.output else None
            return_code = handle_list_command(
                Path(args.path),
                output_path,
                lambda explorer: explorer.list_layouts(),
            )

        case "list-blocks":
            output_path = Path(args.output) if args.output else None
            return_code = handle_list_command(
                Path(args.path),
                output_path,
                lambda explorer: explorer.list_blocks(),
            )

        case "process":
            return_code = handle_process_command(
                Path(args.path),
                workers=max(1, args.workers),
                project_name=args.project_name,
                project_description=args.project_description,
                created_by=args.created_by,
                ai_name_tags=args.ai_name_tags,
                ai_model=args.ai_model,
                ai_base_url=args.ai_base_url,
                ai_api_key=args.ai_api_key,
            )

        case "extract-name-tags":
            return_code = handle_extract_name_tags_command(
                source_path=Path(args.path),
                output_path=Path(args.output) if args.output else None,
                ai_name_tags=args.ai_name_tags,
                ai_model=args.ai_model,
                ai_base_url=args.ai_base_url,
                ai_api_key=args.ai_api_key,
            )

        case "ingest-docs" | "process-docs":
            return_code = handle_process_docs_command(Path(args.path))

        case "project-add":
            return_code = handle_project_add_command(
                name=args.name,
                description=args.description,
                created_by=args.created_by,
            )

        case "project-update":
            return_code = handle_project_update_command(
                project_id=args.project_id,
                name=args.name,
                description=args.description,
                created_by=args.created_by,
            )

        case "project-delete":
            return_code = handle_project_delete_command(
                project_id=args.project_id,
                yes=args.yes,
            )

        case "search":
            output_path = Path(args.output) if args.output else None
            return_code = handle_search_command(
                query=args.query,
                entity_type=args.type,
                limit=args.limit,
                output_path=output_path,
                parent_id=args.parent_id,
            )

        case "index":
            return_code = handle_index_command(
                entity_type=args.type,
                batch_size=args.batch_size,
                reindex=args.reindex,
            )

        case "ask":
            output_path = Path(args.output) if args.output else None
            return_code = handle_ask_command(
                question=args.question,
                entity_type=args.type,
                top_k=args.top_k,
                output_path=output_path,
            )

        case "extract-block":
            explorer = DXFExplorer(args.drawing)
            return_code = explorer.extract_block(args.block_name)

    return return_code


__all__ = ["DXFExplorer", "main"]
