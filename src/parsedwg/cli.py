"""Консольная точка входа для работы с DWG/DXF."""

from __future__ import annotations

import asyncio
import json
import logging
import sys

from pathlib import Path

from . import constants
from .explorer import DXFExplorer
from .process_tree import run_process_tree
from .docs_ingest import run_documents_ingest
from .utils import build_args_parser, out

type ResultRow = dict[str, object]

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.getLogger("ezdxf").disabled = True
logger = logging.getLogger(__name__)

def _save_rows_to_json(output_path: Path, rows: list[ResultRow]) -> None:
    """Сохраняет строки результата в JSON-файл."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def as_table(rows: list[ResultRow]) -> str:
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


def print_as_table(rows: list[ResultRow]) -> None:
    """Выводит строки результата на экран в виде таблицы."""

    out(as_table(rows))


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
        out("Нет результатов.")
        return constants.OK

    if output_path is not None:
        _save_rows_to_json(output_path, rows)
        logger.info("JSON сохранён: %s", output_path)
        return constants.OK

    print_as_table(rows)
    return constants.OK


def handle_index_command(
    entity_type: str | None,
    batch_size: int,
    reindex: bool,
) -> int:
    """Генерирует и сохраняет эмбеддинги для сущностей в БД."""
    from .rag import index_entities

    count = asyncio.run(index_entities(entity_type, batch_size, reindex))
    out(f"Проиндексировано: {count}")
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

    out(result["answer"])
    out("")
    out("Источники:")
    print_as_table(result["sources"])  # type: ignore[arg-type]
    return constants.OK


def handle_process_command(
    source_path: Path,
    workers: int,
    sequential: bool = False,
    dry: bool = False,
    project_name: str | None = None,
    project_description: str | None = None,
    created_by: str | None = None,
    ai_name_tags: bool = False,
    ai_model: str = "llama3.2",
    ai_base_url: str = "http://localhost:11434/v1",
    ai_api_key: str = "ollama",
) -> int:
    """Сканирует DWG/DXF, сохраняет дерево сущностей в БД и привязывает к проекту."""

    try:
        name_tags_config = get_name_tags_config(
            enabled=ai_name_tags,
            model=ai_model,
            base_url=ai_base_url,
            api_key=ai_api_key,
        )
        summary = run_process_tree(
            source_path,
            conversion_workers=workers,
            use_process_pool=not sequential,
            dry_run=dry,
            project_name=project_name,
            project_description=project_description,
            created_by=created_by,
            name_tags_config=name_tags_config,
        )
        if summary.get("dry_run"):
            out("Dry run: запись в БД отключена")
        else:
            out(f"Создан проект: {summary['project_id']}")
        out(f"Найдено файлов: {summary['file_count']}")
        out(f"Обработано файлов: {summary['processed_count']}")
        out(f"Режим обработки: {summary['mode']}")
        out(f"Создано сущностей в БД: {summary['created_entities']}")
        return constants.OK
    except ValueError as e:
        logger.exception("Ошибка при обработке каталога / файла: %s", e)
        return constants.ERROR
    except RuntimeError as e:
        logger.error("Ошибка AI-режима: %s", e)
        return constants.ERROR


def get_name_tags_config(
    enabled: bool,
    model: str,
    base_url: str,
    api_key: str,
):
    """Возвращает конфигурацию для AI-извлечения тегов из имён, или `None`, если 
    режим отключён."""

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
    out(f"Найдено документов: {summary['doc_count']}")
    out(f"Создано сущностей в БД: {summary['created_entities']}")
    out(f"Источник: {summary['source']}")
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

            ensure_config = get_name_tags_config(
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

        out(json.dumps(rows, ensure_ascii=False, indent=2))
        return constants.OK
    except RuntimeError as e:
        logger.error("Ошибка AI-режима: %s", e)
        return constants.ERROR
    except (FileNotFoundError, OSError, ValueError) as e:
        logger.error("Сбой извлечения тегов: %s", e)
        return constants.UNBOUND_ERROR


def handle_extract_token_tags_command(
    tokens: list[str],
    drawing_path: Path | None = None,
    ai_model: str = "llama3.2",
    ai_base_url: str = "http://localhost:11434/v1",
    ai_api_key: str = "ollama",
) -> int:
    """Извлекает JSON-словарь смыслов через LLM для списка токенов."""

    try:
        from .langchain_name_tags import LangChainAgentConfig, LangChainNameTagsExtractor

        merged_tokens: list[str] = []
        seen_tokens: set[str] = set()

        def _extend_unique(values: list[str]) -> None:
            for value in values:
                cleaned = value.strip()
                if not cleaned or cleaned in seen_tokens:
                    continue
                seen_tokens.add(cleaned)
                merged_tokens.append(cleaned)

        _extend_unique(tokens)

        if drawing_path is not None:
            explorer = DXFExplorer(drawing_path)
            _extend_unique(explorer.list_layer_names())

        if not merged_tokens:
            logger.error("Не переданы токены и не указан drawing-файл.")
            return constants.UNBOUND_ERROR

        extractor = LangChainNameTagsExtractor.from_config(
            LangChainAgentConfig(
                model=ai_model,
                base_url=ai_base_url,
                api_key=ai_api_key,
            )
        )
        out(extractor.extract_token_meanings_json(merged_tokens))
        return constants.OK
    except RuntimeError as e:
        logger.error("Ошибка AI-режима: %s", e)
        return constants.ERROR
    except (FileNotFoundError, OSError, ValueError) as e:
        logger.error("Сбой извлечения тегов по токенам: %s", e)
        return constants.UNBOUND_ERROR


def handle_project_add_command(
    name: str,
    description: str | None,
    created_by: str | None,
) -> int:
    """Создаёт проект."""
    from .db import create_project

    project = asyncio.run(create_project(name=name, description=description, created_by=created_by))
    out(f"Проект создан: {project['id']}")
    out(f"Название: {project['name']}")
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
        out("Проект не найден.")
        return constants.NOT_FOUND

    out(f"Проект обновлён: {project['id']}")
    out(f"Название: {project['name']}")
    return constants.OK


def handle_project_delete_command(project_id: str, yes: bool) -> int:
    """Удаляет проект с подтверждением согласия."""
    from .db import delete_project

    if not yes:
        answer = input(
            f"Удалить проект {project_id}? Введите YES для подтверждения: "
        ).strip()
        if answer != "YES":
            out("Удаление отменено.")
            return constants.ERROR

    deleted = asyncio.run(delete_project(project_id=project_id))
    if not deleted:
        out("Проект не найден.")
        return constants.NOT_FOUND

    out(f"Проект удалён: {project_id}")
    return constants.OK


def handle_file_stat_from_db_command(
    file_ref: str,
    by_path: bool,
    output_path: Path | None,
) -> int:
    """Собирает XLSX-статистику по файлу, уже загруженному в БД."""

    import uuid as _uuid

    import openpyxl
    import sqlalchemy as sa
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    from .db import async_session_factory
    from .orm import Entity, EntityType

    async def collect_db_stat():
        async with async_session_factory() as session:
            if by_path:
                file_entity = await session.scalar(
                    sa.select(Entity).where(
                        Entity.entity_type == EntityType.file,
                        Entity.start_from == file_ref,
                    )
                )
            else:
                try:
                    file_uuid = _uuid.UUID(file_ref)
                except ValueError:
                    return None, "Некорректный UUID file_id"
                file_entity = await session.get(Entity, file_uuid)
            if not file_entity:
                return None, "file-сущность не найдена"

            parent_names = []
            parent = file_entity.parent
            while parent:
                parent_names.append(parent.name)
                parent = parent.parent
            parent_dirs = list(reversed(parent_names))

            project = file_entity.project
            project_name = project.name if project else ""

            blocks = await session.execute(
                sa.select(Entity)
                .where(
                    Entity.parent_id == file_entity.id,
                    Entity.entity_type == EntityType.block,
                )
                .order_by(Entity.name.asc())
            )
            blocks = [block for (block,) in blocks.all()]

            table_blocks = [block for block in blocks if block.is_table]

            primitives = await session.execute(
                sa.select(Entity)
                .where(
                    Entity.parent_id.in_([block.id for block in blocks]),
                    Entity.entity_type == EntityType.primitive,
                )
            )
            primitives = [primitive for (primitive,) in primitives.all()]

            return {
                "file": file_entity,
                "parent_dirs": parent_dirs,
                "project": project_name,
                "blocks": blocks,
                "table_blocks": table_blocks,
                "primitives": primitives,
            }, None

    stat, err = asyncio.run(collect_db_stat())
    if err:
        out(f"Ошибка: {err}")
        return constants.ERROR
    assert stat is not None

    file_entity = stat["file"]
    parent_dirs = stat["parent_dirs"]
    project = stat["project"]
    blocks = stat["blocks"]
    table_blocks = stat["table_blocks"]
    primitives = stat["primitives"]

    wb = openpyxl.Workbook()

    ws_file = wb.active
    assert ws_file is not None
    ws_file.title = "Файл"
    ws_file.append(["Параметр", "Значение"])
    fill = PatternFill(fill_type="solid", fgColor="D9D9D9")
    font = Font(bold=True)
    for cell in ws_file[1]:
        cell.fill = fill
        cell.font = font
    ws_file.append(["Имя файла", file_entity.name])
    ws_file.append(["MD5", file_entity.file_md5 or ""])
    ws_file.append(["Родительские каталоги", " / ".join(parent_dirs)])
    ws_file.append(["Проект", project])
    ws_file.freeze_panes = "A2"
    for row in ws_file.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for col_idx, col_cells in enumerate(ws_file.iter_cols(), start=1):
        values = [str(cell.value) for cell in col_cells if cell.value is not None]
        width = max((len(line) for value in values for line in value.splitlines()), default=10)
        ws_file.column_dimensions[get_column_letter(col_idx)].width = min(width + 2, 60)

    ws_blocks = wb.create_sheet("Блоки")
    headers_blocks = ["Наименование", "Таблица", "Добавлен (раз)", "Слои"]
    ws_blocks.append(headers_blocks)
    for cell in ws_blocks[1]:
        cell.fill = fill
        cell.font = font
    ws_blocks.freeze_panes = "A2"
    for block in blocks:
        ws_blocks.append([
            block.name,
            "Да" if block.is_table else "Нет",
            "-",
            "-",
        ])
    for row in ws_blocks.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for col_idx, col_cells in enumerate(ws_blocks.iter_cols(), start=1):
        values = [str(cell.value) for cell in col_cells if cell.value is not None]
        width = max((len(line) for value in values for line in value.splitlines()), default=10)
        ws_blocks.column_dimensions[get_column_letter(col_idx)].width = min(width + 2, 60)

    ws_tables = wb.create_sheet("Блоки-таблицы")
    ws_tables.append(headers_blocks)
    for cell in ws_tables[1]:
        cell.fill = fill
        cell.font = font
    ws_tables.freeze_panes = "A2"
    for block in table_blocks:
        ws_tables.append([
            block.name,
            "Да",
            "-",
            "-",
        ])
    for row in ws_tables.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for col_idx, col_cells in enumerate(ws_tables.iter_cols(), start=1):
        values = [str(cell.value) for cell in col_cells if cell.value is not None]
        width = max((len(line) for value in values for line in value.splitlines()), default=10)
        ws_tables.column_dimensions[get_column_letter(col_idx)].width = min(width + 2, 60)

    ws_prim = wb.create_sheet("Текстовые примитивы")
    headers_prim = ["Блок", "Тип", "Текст", "Слой", "Локация"]
    ws_prim.append(headers_prim)
    for cell in ws_prim[1]:
        cell.fill = fill
        cell.font = font
    ws_prim.freeze_panes = "A2"
    for primitive in primitives:
        ws_prim.append([
            primitive.data.get("block", "") if primitive.data else "",
            primitive.data.get("type", "") if primitive.data else "",
            primitive.data.get("text", "") if primitive.data else "",
            primitive.data.get("layer", "") if primitive.data else "",
            primitive.data.get("location", "") if primitive.data else "",
        ])
    for row in ws_prim.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for col_idx, col_cells in enumerate(ws_prim.iter_cols(), start=1):
        values = [str(cell.value) for cell in col_cells if cell.value is not None]
        width = max((len(line) for value in values for line in value.splitlines()), default=10)
        ws_prim.column_dimensions[get_column_letter(col_idx)].width = min(width + 2, 60)

    if output_path is None:
        if by_path:
            stem = Path(file_ref).stem
            output_path = Path(f"{stem}_dbstat.xlsx")
        else:
            output_path = Path(f"{file_ref}_dbstat.xlsx")
    wb.save(output_path)
    out(f"Статистика по файлу из БД сохранена: {output_path}")
    return constants.OK


def main(argv: list[str] | None = None) -> int:
    """Точка входа для командной строки."""

    parser = build_args_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(argv)

    return_code: int = 0
    match args.command:

        case "process":
            return_code = handle_process_command(
                Path(args.path),
                workers=max(1, args.workers),
                sequential=args.sequential,
                dry=args.dry,
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

        case "extract-token-tags":
            return_code = handle_extract_token_tags_command(
                tokens=args.tokens,
                drawing_path=Path(args.drawing) if args.drawing else None,
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

        case "file-stat":
            drawing_path = Path(args.drawing)
            output_path = Path(args.output) if args.output else drawing_path.with_suffix(".xlsx")
            project = args.project or ""
            explorer = DXFExplorer(drawing_path)
            explorer.export_file_stat(output_path, project=project)


            if args.db_tables_by_id:
                from .db import get_file_id_by_source, get_table_blocks_by_file_id
                file_id = asyncio.run(get_file_id_by_source(str(drawing_path)))
                if file_id:
                    table_blocks = asyncio.run(get_table_blocks_by_file_id(file_id))
                    exported_tables = explorer.export_tables_from_db(
                        table_blocks=table_blocks,
                        output_dir=output_path.parent,
                    )
                    out(f"Таблиц из БД по file_id выгружено: {len(exported_tables)}")
                else:
                    out("file_id не найден для данного файла (source_ref)")

            elif args.db_tables:
                from .db import get_table_blocks_for_source
                table_blocks = asyncio.run(get_table_blocks_for_source(str(drawing_path)))
                exported_tables = explorer.export_tables_from_db(
                    table_blocks=table_blocks,
                    output_dir=output_path.parent,
                )
                out(f"Таблиц из БД по source_ref выгружено: {len(exported_tables)}")

            out(f"Статистика сохранена: {output_path}")
            return_code = constants.OK

        case "file-stat-from-db":
            return_code = handle_file_stat_from_db_command(
                file_ref=args.file_ref,
                by_path=args.by_path,
                output_path=Path(args.output) if args.output else None,
            )


    return return_code


__all__ = ["DXFExplorer", "main"]
