"""Console entry point for working with DWG/DXF."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import tempfile
import time

from pathlib import Path

from .langchain_name_tags import LangChainAgentConfig, LangChainNameTagsExtractor


from . import constants
from .dxf_analyzer import DXFAnalyzer
from .settings import settings
from .explorer import DXFExplorer
from .process_tree import run_process_tree
from .docs_ingest import run_documents_ingest
from .utils import build_args_parser, out

type ResultRow = dict[str, object]

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(filename)s - %(levelname)s - %(message)s",
)
logging.getLogger("ezdxf").disabled = True
logging.getLogger('fontTools.ttLib.ttFont').setLevel(logging.WARNING)
logging.getLogger('matplotlib.font_manager').disabled = True
logger = logging.getLogger(__name__)


def _write_progress_line(message: str, previous_width: int = 0) -> int:
    """Update a single progress line in stdout."""

    width = max(previous_width, len(message))
    sys.stdout.write("\r" + message.ljust(width))
    sys.stdout.flush()
    return width


def _finish_progress_line(width: int) -> None:
    """Finish the progress line with a newline."""

    if width <= 0:
        return
    sys.stdout.write("\n")
    sys.stdout.flush()


def _format_duration_seconds(duration_seconds: float) -> str:
    """Format processing duration in seconds."""

    return f"{duration_seconds:.2f} c"

def _save_rows_to_json(output_path: Path, rows: list[ResultRow]) -> None:
    """Save result rows to a JSON file."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def as_table(rows: list[ResultRow]) -> str:
    """Format result rows as a simple ASCII table."""

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
    """Print result rows as a table."""

    out(as_table(rows))


def handle_search_command(
    query: str,
    entity_type: str | None,
    limit: int,
    output_path: Path | None,
    parent_id: str | None = None,
) -> int:
    """Run full-text search against the PostgreSQL entity table."""
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
    """Generate and store embeddings for DB entities."""
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
    """RAG request: vector search plus answer generation via llama."""
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
    dry: bool = False,
    project_name: str | None = None,
    project_description: str | None = None,
    created_by: str | None = None,
    ai_name_tags: bool = False,
    ai_model: str = settings.ollama_llm_model,
    ai_base_url: str = settings.ollama_base_url,
    ai_api_key: str = ""
) -> int:
    """Scan DWG/DXF content, save the entity tree to the DB, and attach it to a project."""

    try:
        name_tags_config = get_name_tags_config(
            enabled=ai_name_tags,
            model=ai_model,
            base_url=ai_base_url,
            api_key=ai_api_key,
        )
        summary = run_process_tree(
            source_path,
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
    """Return config for AI tag extraction from names, or None if disabled."""

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
    """Recursively index PDF/DOCX/XLSX/CSV documents into the entity table."""

    summary = run_documents_ingest(source_path)
    out(f"Найдено документов: {summary['doc_count']}")
    out(f"Создано сущностей в БД: {summary['created_entities']}")
    out(f"Источник: {summary['source']}")
    return constants.OK


def handle_export_block_png_command(
    drawing_path: Path,
    block_name: str,
    output_path: Path | None,
    dpi: int,
) -> int:
    """Export the selected block to PNG."""

    try:
        explorer = DXFExplorer(drawing_path)
        saved_path = explorer.export_block_png(block_name, output_path=output_path, dpi=dpi)
        out(f"PNG сохранён: {saved_path}")
        return constants.OK
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        logger.error("Не удалось экспортировать блок в PNG: %s", exc)
        return constants.ERROR


def handle_export_block_svg_command(
    drawing_path: Path,
    block_name: str,
    output_path: Path | None,
) -> int:
    """Export the selected block to SVG."""

    try:
        explorer = DXFExplorer(drawing_path)
        saved_path = explorer.export_block_svg(block_name, output_path=output_path)
        out(f"SVG сохранён: {saved_path}")
        return constants.OK
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        logger.error("Не удалось экспортировать блок в SVG: %s", exc)
        return constants.ERROR


def handle_extract_name_tags_command(
    source_path: Path,
    output_path: Path | None,
    ai_name_tags: bool = False,
    ai_model: str = "llama3.1:8b",
    ai_base_url: str = "http://localhost:11434/v1",
    ai_api_key: str = "ollama",
) -> int:
    """Extract semantic tags from file and directory names."""
    from .name_tags import collect_name_tags

    try:
        ai_extractor = None
        if ai_name_tags:
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
    with_scores: bool = False,
) -> int:
    """Extract a JSON mapping of meanings via LLM for a token list."""
    token_context = "строительство, чертеж"

    try:
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
        if with_scores:
            out(
                extractor.extract_token_meanings_scored_json(
                    merged_tokens,
                    extra_context=token_context,
                )
            )
        else:
            out(
                extractor.extract_token_meanings_json(
                    merged_tokens,
                    extra_context=token_context,
                )
            )
        return constants.OK
    except RuntimeError as e:
        logger.error("Ошибка AI-режима: %s", e)
        return constants.ERROR
    except (FileNotFoundError, OSError, ValueError) as e:
        logger.error("Сбой извлечения тегов по токенам: %s", e)
        return constants.UNBOUND_ERROR


def _derive_ollama_chat_url(base_url: str) -> str:
    """Build an Ollama /api/chat URL from an OpenAI-compatible base URL."""
    stripped = base_url.rstrip("/")
    if stripped.endswith("/v1"):
        stripped = stripped[:-3]
    return stripped.rstrip("/") + "/api/chat"


def _derive_openai_chat_completions_url(base_url: str) -> str:
    """Build an OpenAI-compatible v1/chat/completions URL from a base URL."""
    stripped = base_url.rstrip("/")
    if stripped.endswith("/v1"):
        return stripped + "/chat/completions"
    return stripped + "/v1/chat/completions"


def handle_extract_name_meaning_command(
    name: str | None = None,
    entity_id: str | None = None,
    extra_context: str = "",
    ai_model: str = "llama3.1:8b",
    ai_base_url: str = "http://localhost:11434/v1",
    ai_api_key: str = "ollama",
) -> int:
    """Analyze a title or DB entity name via LLM."""
    from .db import get_entity_name_by_id
    from .langchain_name_tags import call_openai_chat_completions_name_meaning

    if bool(name) == bool(entity_id):
        logger.error("Нужно указать либо name, либо --entity-id.")
        return constants.UNBOUND_ERROR

    resolved_name = name
    if entity_id is not None:
        try:
            resolved_name = asyncio.run(get_entity_name_by_id(entity_id))
        except (ValueError, LookupError) as exc:
            logger.error("Некорректный entity_id: %s", exc)
            return constants.UNBOUND_ERROR
        if resolved_name is None:
            out(f"Сущность не найдена: {entity_id}")
            return constants.NOT_FOUND
        out(f"Сущность: {resolved_name}")
        out("")

    assert resolved_name is not None
    normalized_name = " ".join(resolved_name.split())
    normalized_extra_context = " ".join(extra_context.split())
    completions_url = _derive_openai_chat_completions_url(ai_base_url)

    try:
        result = call_openai_chat_completions_name_meaning(
            name=normalized_name,
            completions_url=completions_url,
            model=ai_model,
            extra_context=normalized_extra_context,
            api_key=ai_api_key,
        )
        out(result)
        return constants.OK
    except RuntimeError as e:
        logger.error("Ошибка AI-режима: %s", e)
        return constants.ERROR


def handle_explain_block_command(
    block_id: str,
    extra_context: str = "",
    ai_model: str = "llama3.1:8b",
    ai_base_url: str = "http://localhost:11434/v1",
    ai_api_key: str = "ollama",
) -> int:
    """Fetch a block name by UUID from the DB and analyze it via LLM."""
    _ = ai_api_key  # Ollama /api/chat не требует авторизации

    from .db import get_entity_name_by_id

    try:
        name = asyncio.run(get_entity_name_by_id(block_id))
    except (ValueError, LookupError) as e:
        logger.error("Некорректный block_id: %s", e)
        return constants.UNBOUND_ERROR

    if name is None:
        out(f"Блок не найден: {block_id}")
        return constants.NOT_FOUND

    out(f"Блок: {name}")
    out("")
    return handle_extract_name_meaning_command(
        name=name,
        entity_id=None,
        extra_context=extra_context,
        ai_model=ai_model,
        ai_base_url=ai_base_url,
        ai_api_key=ai_api_key,
    )


def handle_categorize_entities_command(
    entity_ids: list[str] | None,
    entity_type: str | None,
    ai_model: str = "llama3.2",
    ai_base_url: str = "http://localhost:11434/v1",
    ai_api_key: str = "ollama",
    workers: int = 1,
    dry: bool = False,
) -> int:
    """Extract semantic categories for entities and link them in the DB."""
    extra_context = "строительство, чертеж"

    from .db import assign_semantic_category, list_entities_for_semantic_categorization

    if bool(entity_ids) == bool(entity_type):
        logger.error("Нужно указать либо --entity-id, либо --entity-type.")
        return constants.UNBOUND_ERROR
    if workers <= 0:
        logger.error("--workers должен быть больше 0.")
        return constants.UNBOUND_ERROR

    def _build_dry_row(entity: dict[str, str], meanings: list[dict[str, object]]) -> dict[str, object]:
        normalized_meanings = [
            {
                "meaning": str(item.get("meaning")),
                "score": item.get("score"),
            }
            for item in meanings
            if isinstance(item, dict) and isinstance(item.get("meaning"), str)
        ]
        category_name = normalized_meanings[0]["meaning"] if normalized_meanings else ""
        return {
            "entity_id": str(entity["id"]),
            "entity_name": str(entity["name"]),
            "entity_type": str(entity["entity_type"]),
            "category_id": "",
            "category_name": category_name,
            "matched_meaning": category_name,
            "status": "dry-run" if normalized_meanings else "no-tags",
            "meanings": normalized_meanings,
        }

    async def _run_stream() -> list[dict[str, object]]:
        selected_entities = await list_entities_for_semantic_categorization(
            entity_ids=entity_ids,
            entity_type=entity_type,
        )
        if not selected_entities:
            return []
        if not dry:
            out(f"Выбрано сущностей: {len(selected_entities)}")

        queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
        semaphore = asyncio.Semaphore(workers)

        async def _extract_entity(entity: dict[str, str]) -> dict[str, object]:
            async with semaphore:
                text = "\n".join(
                    part.strip()
                    for part in [
                        str(entity["name"]),
                        str(entity["description"]),
                    ]
                    if str(part).strip()
                )
                meanings = await asyncio.to_thread(
                    extractor.extract_scored_tags,
                    text,
                    extra_context,
                )
                return {
                    "entity": entity,
                    "entity_id": entity["id"],
                    "meanings": meanings,
                }

        async def producer() -> None:
            try:
                tasks = [asyncio.create_task(_extract_entity(entity)) for entity in selected_entities]
                for task in asyncio.as_completed(tasks):
                    await queue.put(await task)
            except (RuntimeError, OSError, ValueError) as exc:
                await queue.put({"exception": exc})
            finally:
                await queue.put(None)

        async def consumer() -> list[dict[str, object]]:
            rows: list[dict[str, object]] = []
            total = len(selected_entities)
            progress_width = 0
            while True:
                item = await queue.get()
                try:
                    if item is None:
                        if not dry:
                            _finish_progress_line(progress_width)
                        return rows
                    if "exception" in item:
                        raise item["exception"]  # type: ignore[misc]
                    raw_meanings = item.get("meanings", [])
                    normalized_meanings = (
                        [value for value in raw_meanings if isinstance(value, dict)]
                        if isinstance(raw_meanings, list)
                        else []
                    )
                    if dry:
                        entity_payload = item.get("entity")
                        if not isinstance(entity_payload, dict):
                            raise ValueError("Некорректная сущность в dry-режиме категоризации.")
                        rows.append(_build_dry_row(entity_payload, normalized_meanings))
                        continue

                    saved_row = await assign_semantic_category(
                        entity_id=str(item["entity_id"]),
                        meanings=normalized_meanings,
                    )
                    rows.append(saved_row)
                    progress_width = _write_progress_line(
                        "Сохранено {current}/{total}: {entity_id} -> {category_name} [{status}]".format(
                            current=len(rows),
                            total=total,
                            entity_id=saved_row["entity_id"],
                            category_name=saved_row["category_name"] or "-",
                            status=saved_row["status"],
                        ),
                        previous_width=progress_width,
                    )
                finally:
                    queue.task_done()

        producer_task = asyncio.create_task(producer())
        consumer_task = asyncio.create_task(consumer())
        await producer_task
        await queue.join()
        return await consumer_task

    try:
        extractor = LangChainNameTagsExtractor.from_config(
            LangChainAgentConfig(
                model=ai_model,
                base_url=ai_base_url,
                api_key=ai_api_key,
            )
        )

        rows = asyncio.run(_run_stream())
        if not rows:
            if dry:
                out("[]")
            else:
                out("Нет сущностей для категоризации.")
            return constants.OK
        if dry:
            out(json.dumps(rows, ensure_ascii=False, indent=2))
            return constants.OK
        printable_rows: list[ResultRow] = []
        for row in rows:
            raw_meanings = row.get("meanings", [])
            printable_rows.append(
                {
                    "entity_id": row["entity_id"],
                    "entity_type": row["entity_type"],
                    "entity_name": row["entity_name"],
                    "category_name": row["category_name"],
                    "matched_meaning": row["matched_meaning"],
                    "status": row["status"],
                    "meanings": ", ".join(str(value) for value in raw_meanings)
                    if isinstance(raw_meanings, list)
                    else "",
                }
            )
        print_as_table(printable_rows)
        return constants.OK
    except RuntimeError as e:
        logger.error("Ошибка AI-режима: %s", e)
        return constants.ERROR
    except (LookupError, OSError, ValueError) as e:
        logger.error("Сбой категоризации сущностей: %s", e)
        return constants.UNBOUND_ERROR


def handle_interpret_entities_command(
    entity_ids: list[str] | None,
    entity_type: str | None,
    extra_context: str = "",
    ai_model: str = "llama3.1:8b",
    ai_base_url: str = "http://localhost:11434/v1",
    ai_api_key: str = "ollama",
    workers: int = 1,
    dry: bool = False,
) -> int:
    """Request LLM name interpretations for entities by id or type.

    Save the result into the short_interpretation field.
    """

    logger.info("Стартуем")

    from .db import list_entities_for_semantic_categorization, save_short_interpretation
    from .langchain_name_tags import (
        build_name_meaning_prompt,
        call_openai_chat_completions_name_meaning,
    )

    if bool(entity_ids) == bool(entity_type):
        logger.error("Нужно указать либо --entity-id, либо --entity-type.")
        return constants.UNBOUND_ERROR
    if workers <= 0:
        logger.error("--workers должен быть больше 0.")
        return constants.UNBOUND_ERROR

    chat_url = _derive_openai_chat_completions_url(ai_base_url)
    logger.debug("chat_url: %s", chat_url)
    normalized_context = " ".join(extra_context.split())
    llm_timeout_seconds = settings.ollama_timeout_seconds

    async def _run() -> dict[str, object]:
        entities = await list_entities_for_semantic_categorization(
            entity_ids=entity_ids,
            entity_type=entity_type,
        )
        if not entities:
            return {"rows": [], "failures": []}
        if not dry:
            out(f"Выбрано сущностей: {len(entities)}")

        semaphore = asyncio.Semaphore(workers)

        async def _process(entity: dict[str, str]) -> dict[str, object]:
            async with semaphore:
                prompt = build_name_meaning_prompt(
                    name=entity["name"],
                    extra_context=normalized_context,
                )
                logger.debug(
                    "LLM запрос interpret-entities: entity_id=%s entity_name=%s model=%s chat_url=%s\n%s",
                    entity["id"],
                    entity["name"],
                    ai_model,
                    chat_url,
                    prompt,
                )
                try:
                    text = await asyncio.wait_for(
                        asyncio.to_thread(
                            call_openai_chat_completions_name_meaning,
                            name=entity["name"],
                            completions_url=chat_url,
                            model=ai_model,
                            extra_context=normalized_context,
                            timeout_seconds=llm_timeout_seconds,
                            api_key=ai_api_key,
                        ),
                        timeout=llm_timeout_seconds + 5.0,
                    )
                except TimeoutError:
                    return {
                        "status": "error",
                        "entity_id": entity["id"],
                        "entity_name": entity["name"],
                        "error": (
                            "Превышен таймаут ожидания ответа LLM для сущности "
                            f"{entity['id']} ({entity['name']})."
                        ),
                    }
                except (OSError, RuntimeError, ValueError) as exc:
                    return {
                        "status": "error",
                        "entity_id": entity["id"],
                        "entity_name": entity["name"],
                        "error": str(exc),
                    }
                logger.debug(
                    "LLM ответ interpret-entities: entity_id=%s entity_name=%s\n%s",
                    entity["id"],
                    entity["name"],
                    text,
                )
                return {
                    "status": "ok",
                    "entity_id": entity["id"],
                    "entity_name": entity["name"],
                    "text": text,
                }

        rows: list[dict[str, object]] = []
        failures: list[dict[str, object]] = []
        total = len(entities)
        progress_width = 0
        tasks = [asyncio.create_task(_process(entity)) for entity in entities]
        try:
            for task in asyncio.as_completed(tasks):
                item = await task
                entity_id = str(item.get("entity_id", ""))
                entity_name = str(item.get("entity_name", ""))
                if item.get("status") == "error":
                    failures.append(
                        {
                            "status": "error",
                            "entity_id": entity_id,
                            "entity_name": entity_name,
                            "error": str(item.get("error", "")),
                        }
                    )
                    logger.error(
                        "Ошибка интерпретации сущности %s (%s): %s",
                        entity_id or "-",
                        entity_name or "-",
                        item.get("error", ""),
                    )
                else:
                    text = str(item["text"])
                    try:
                        if dry:
                            rows.append(
                                {
                                    "entity_id": entity_id,
                                    "entity_name": entity_name,
                                    "text": text,
                                    "status": "ok",
                                }
                            )
                        else:
                            logger.debug(
                                "Сохраняем интерпретацию для сущности %s (%s): %s",
                                entity_id,
                                entity_name,
                                text,
                            )
                            await save_short_interpretation(entity_id, text)
                            rows.append({"entity_id": entity_id, "entity_name": entity_name})
                    except (LookupError, OSError, RuntimeError, ValueError) as exc:
                        failures.append(
                            {
                                "status": "error",
                                "entity_id": entity_id,
                                "entity_name": entity_name,
                                "error": str(exc),
                            }
                        )
                        logger.error(
                            "Ошибка сохранения интерпретации сущности %s (%s): %s",
                            entity_id or "-",
                            entity_name or "-",
                            exc,
                        )

                processed = len(rows) + len(failures)
                if not dry:
                    progress_width = _write_progress_line(
                        "Обработано {processed}/{total}: успешно {success}, ошибок {errors}".format(
                            processed=processed,
                            total=total,
                            success=len(rows),
                            errors=len(failures),
                        ),
                        previous_width=progress_width,
                    )
        finally:
            if not dry:
                _finish_progress_line(progress_width)

        return {"rows": rows, "failures": failures}

    try:
        result = asyncio.run(_run())
        rows = result.get("rows", [])
        if not isinstance(rows, list):
            rows = []
        failures = result.get("failures", [])
        if not isinstance(failures, list):
            failures = []
        if not rows:
            if failures:
                logger.error("Не удалось интерпретировать ни одной сущности. Ошибок: %d", len(failures))
                return constants.ERROR
            out("Нет сущностей для интерпретации.")
            return constants.OK
        if dry:
            out(json.dumps(rows + failures, ensure_ascii=False, indent=2))
            return constants.OK
        out(f"Интерпретировано: {len(rows)}")
        if failures:
            out(f"Ошибок: {len(failures)}")
        return constants.OK
    except RuntimeError as e:
        logger.error("Ошибка AI-режима: %s", e)
        return constants.ERROR
    except (LookupError, OSError, ValueError, TimeoutError) as e:
        logger.error("Сбой интерпретации сущностей: %s", e)
        return constants.UNBOUND_ERROR


def handle_interpret_blocks_command(
    block_ids: list[str] | None,
    file_ref: str | None,
    by_path: bool,
    extra_context: str = "",
    ai_model: str = "llama3.1:8b",
    ai_base_url: str = "http://localhost:11434/v1",
    ai_api_key: str = "ollama",
    workers: int = 1,
    dry: bool = False,
) -> int:
    """Interpret blocks and save short/full interpretations."""

    from .db import (
        get_file_id_by_source,
        get_full_description,
        list_blocks_for_interpretation,
        save_block_description,
        save_block_interpretations,
    )
    from .langchain_name_tags import call_openai_chat_completions_name_meaning

    if bool(block_ids) == bool(file_ref):
        logger.error("Нужно указать либо --block-id, либо file_ref.")
        return constants.UNBOUND_ERROR
    if workers <= 0:
        logger.error("--workers должен быть больше 0.")
        return constants.UNBOUND_ERROR

    resolved_file_id = file_ref
    if file_ref is not None and by_path:
        resolved_file_id = asyncio.run(get_file_id_by_source(file_ref))
        if not resolved_file_id:
            out("Файл не найден в БД.")
            return constants.NOT_FOUND

    completions_url = _derive_openai_chat_completions_url(ai_base_url)
    normalized_context = " ".join(extra_context.split())
    llm_timeout_seconds = settings.ollama_timeout_seconds

    async def _run() -> dict[str, object]:
        blocks = await list_blocks_for_interpretation(
            block_ids=block_ids,
            file_id=resolved_file_id,
        )
        if not blocks:
            return {"rows": [], "failures": []}
        if not dry:
            out(f"Выбрано блоков: {len(blocks)}")

        semaphore = asyncio.Semaphore(workers)

        async def _process(block: dict[str, str]) -> dict[str, object]:
            async with semaphore:
                block_id = block["id"]
                block_name = block["name"]
                block_file_id = block.get("file_id") or resolved_file_id
                started_at = time.perf_counter()
                try:
                    block_payload = await get_full_description(
                        block_name,
                        file_id=block_file_id,
                    )
                    block_text_for_llm = (
                        json.dumps(block_payload, ensure_ascii=False, sort_keys=True)
                        if block_payload is not None
                        else block_name
                    )
                    if not dry and block_payload is not None:
                        await save_block_description(
                            block_id=block_id,
                            description=block_text_for_llm,
                        )
                    short_interpretation = await asyncio.wait_for(
                        asyncio.to_thread(
                            call_openai_chat_completions_name_meaning,
                            name=block_name,
                            completions_url=completions_url,
                            model=ai_model,
                            extra_context=normalized_context,
                            timeout_seconds=llm_timeout_seconds,
                            api_key=ai_api_key,
                        ),
                        timeout=llm_timeout_seconds + 5.0,
                    )
                    # Request the full block description from the LLM as well.
                    full_description = await asyncio.wait_for(
                        asyncio.to_thread(
                            call_openai_chat_completions_name_meaning,
                            name=block_text_for_llm,
                            completions_url=completions_url,
                            model=ai_model,
                            extra_context=normalized_context + "\nДай максимально подробное описание назначения и структуры этого блока, с деталями для проектировщика.",
                            timeout_seconds=llm_timeout_seconds,
                            api_key=ai_api_key,
                        ),
                        timeout=llm_timeout_seconds + 10.0,
                    )
                    block_description = block_payload
                    full_interpretation = full_description
                except TimeoutError:
                    duration_seconds = round(time.perf_counter() - started_at, 3)
                    return {
                        "status": "error",
                        "block_id": block_id,
                        "block_name": block_name,
                        "duration_seconds": duration_seconds,
                        "error": (
                            "Превышен таймаут ожидания ответа LLM для блока "
                            f"{block_id} ({block_name})."
                        ),
                    }
                except (LookupError, OSError, RuntimeError, ValueError) as exc:
                    duration_seconds = round(time.perf_counter() - started_at, 3)
                    return {
                        "status": "error",
                        "block_id": block_id,
                        "block_name": block_name,
                        "duration_seconds": duration_seconds,
                        "error": str(exc),
                    }
                duration_seconds = round(time.perf_counter() - started_at, 3)
                return {
                    "status": "ok",
                    "block_id": block_id,
                    "block_name": block_name,
                    "duration_seconds": duration_seconds,
                    "short_interpretation": short_interpretation,
                    "description": block_description,
                    "full_interpretation": full_interpretation,
                }

        rows: list[dict[str, object]] = []
        failures: list[dict[str, object]] = []
        progress_width = 0
        total = len(blocks)
        tasks = [asyncio.create_task(_process(block)) for block in blocks]
        try:
            for task in asyncio.as_completed(tasks):
                item = await task
                block_id = str(item.get("block_id", ""))
                block_name = str(item.get("block_name", ""))
                raw_duration_seconds = item.get("duration_seconds", 0.0)
                duration_seconds = (
                    float(raw_duration_seconds)
                    if isinstance(raw_duration_seconds, (int, float))
                    else 0.0
                )
                duration_label = _format_duration_seconds(duration_seconds)
                if item.get("status") == "error":
                    failures.append(
                        {
                            "status": "error",
                            "block_id": block_id,
                            "block_name": block_name,
                            "duration_seconds": duration_seconds,
                            "error": str(item.get("error", "")),
                        }
                    )
                    logger.error(
                        "Ошибка интерпретации блока %s (%s) за %s: %s",
                        block_id or "-",
                        block_name or "-",
                        duration_label,
                        item.get("error", ""),
                    )
                else:
                    short_interpretation = str(item["short_interpretation"])
                    block_description = str(item["description"])
                    full_interpretation = str(item["full_interpretation"])
                    try:
                        if dry:
                            rows.append(
                                {
                                    "status": "ok",
                                    "block_id": block_id,
                                    "block_name": block_name,
                                    "duration_seconds": duration_seconds,
                                    "short_interpretation": short_interpretation,
                                    "description": block_description,
                                    "full_interpretation": full_interpretation,
                                }
                            )
                        else:
                            await save_block_interpretations(
                                block_id=block_id,
                                short_interpretation=short_interpretation,
                                full_interpretation=full_interpretation,
                                description=block_description,
                            )
                            rows.append(
                                {
                                    "block_id": block_id,
                                    "block_name": block_name,
                                    "duration_seconds": duration_seconds,
                                }
                            )
                    except (LookupError, OSError, RuntimeError, ValueError) as exc:
                        failures.append(
                            {
                                "status": "error",
                                "block_id": block_id,
                                "block_name": block_name,
                                "duration_seconds": duration_seconds,
                                "error": str(exc),
                            }
                        )
                        logger.error(
                            "Ошибка сохранения интерпретации блока %s (%s): %s",
                            block_id or "-",
                            block_name or "-",
                            exc,
                        )

                if not dry:
                    out(
                        f"\nБлок {block_name or block_id or '-'} обработан за {duration_label}"
                    )

                processed = len(rows) + len(failures)
                if not dry:
                    progress_width = _write_progress_line(
                        "Обработано {processed}/{total}: успешно {success}, ошибок {errors}".format(
                            processed=processed,
                            total=total,
                            success=len(rows),
                            errors=len(failures),
                        ),
                        previous_width=progress_width,
                    )
        finally:
            if not dry:
                _finish_progress_line(progress_width)

        return {"rows": rows, "failures": failures}

    try:
        result = asyncio.run(_run())
        rows = result.get("rows", [])
        if not isinstance(rows, list):
            rows = []
        failures = result.get("failures", [])
        if not isinstance(failures, list):
            failures = []
        if not rows:
            if failures:
                logger.error("Не удалось интерпретировать ни одного блока. Ошибок: %d", len(failures))
                return constants.ERROR
            out("Нет блоков для интерпретации.")
            return constants.OK
        if dry:
            out(json.dumps(rows + failures, ensure_ascii=False, indent=2))
            return constants.OK
        out(f"Интерпретировано блоков: {len(rows)}")
        if failures:
            out(f"Ошибок: {len(failures)}")
        return constants.OK
    except RuntimeError as e:
        logger.error("Ошибка AI-режима: %s", e)
        return constants.ERROR
    except (LookupError, OSError, ValueError, TimeoutError) as e:
        logger.error("Сбой интерпретации блоков: %s", e)
        return constants.UNBOUND_ERROR


def handle_verify_extraction_command(
    drawing_path: Path,
    file_id: str | None = None,
) -> int:
    """Compare DWG/DXF file contents with what is already stored in the DB."""

    from .verify_extraction import format_verification_report, verify_extraction

    try:
        report = asyncio.run(verify_extraction(drawing_path, file_id=file_id))
        out(format_verification_report(report))
        return constants.OK if report["ok"] else constants.ERROR
    except LookupError as e:
        logger.error("Файл не найден в БД: %s", e, exc_info=True)
        return constants.NOT_FOUND
    except (FileNotFoundError, OSError, ValueError) as e:
        logger.error("Ошибка верификации: %s", e)
        return constants.ERROR


def _resolve_source_ref_to_drawing_path(source_ref: str, temp_dir: Path) -> Path:
    from .process_tree import DWGTreeProcessor

    if "::" not in source_ref:
        return Path(source_ref)

    archive_path_str, member_name = source_ref.split("::", 1)
    return DWGTreeProcessor.extract_from_zip(Path(archive_path_str), member_name, temp_dir)


def _get_block_layout_by_name(doc, block_name: str):
    for layout in doc.layouts:
        if str(layout.name) == block_name:
            return layout
    for block in doc.blocks:
        if str(block.name) == block_name:
            return block
    if block_name == "Model" or block_name.startswith("*Model_Space"):
        return doc.modelspace()
    return None


def _format_point_payload(point: object | None) -> list[float] | None:
    if point is None:
        return None
    x = getattr(point, "x", None)
    y = getattr(point, "y", None)
    z = getattr(point, "z", 0.0)
    if x is None or y is None:
        return None
    return [float(x), float(y), float(z)]


def _collect_mleader_nearest_rows(
    entities: list[dict[str, str]],
    search_types: tuple[str, ...] = ("LINE", "CIRCLE", "LWPOLYLINE"),
) -> list[dict[str, object]]:
    from .process_tree import DWGTreeProcessor
    from .utils import (
        find_closest_entity_in_entities,
        get_mleader_annotation_text,
        get_mleader_target_point,
    )

    by_source: dict[str, list[dict[str, str]]] = {}
    for entity in entities:
        source_ref = str(entity.get("source_ref", "")).strip()
        by_source.setdefault(source_ref, []).append(entity)

    rows: list[dict[str, object]] = []
    for source_ref, source_entities in by_source.items():
        if not source_ref:
            for entity in source_entities:
                rows.append(
                    {
                        "status": "error",
                        "entity_id": entity["id"],
                        "file_id": entity.get("file_id", ""),
                        "source_ref": source_ref,
                        "block": entity.get("block", ""),
                        "layer": entity.get("layer", ""),
                        "matching_strategy": "source_ref+block+ordinal",
                        "error": "У MULTILEADER отсутствует source_ref исходного файла.",
                    }
                )
            continue

        grouped_by_block: dict[str, list[dict[str, str]]] = {}
        for entity in source_entities:
            grouped_by_block.setdefault(str(entity.get("block", "")), []).append(entity)

        try:
            with tempfile.TemporaryDirectory(prefix="parsedwg-mleader-") as temp_dir_name:
                temp_dir = Path(temp_dir_name)
                drawing_path = _resolve_source_ref_to_drawing_path(source_ref, temp_dir)
                doc = DWGTreeProcessor.read_drawing(drawing_path)
                for block_name, block_entities in grouped_by_block.items():
                    layout = _get_block_layout_by_name(doc, block_name)
                    if layout is None:
                        for entity in block_entities:
                            rows.append(
                                {
                                    "status": "error",
                                    "entity_id": entity["id"],
                                    "file_id": entity.get("file_id", ""),
                                    "source_ref": source_ref,
                                    "block": block_name,
                                    "layer": entity.get("layer", ""),
                                    "matching_strategy": "source_ref+block+ordinal",
                                    "error": f"Блок {block_name!r} не найден в исходном чертеже.",
                                }
                            )
                        continue

                    mleader_objects = [
                        drawing_entity
                        for drawing_entity in layout
                        if str(drawing_entity.dxftype()) == "MULTILEADER"
                    ]
                    for ordinal, entity in enumerate(block_entities):
                        base_row = {
                            "entity_id": entity["id"],
                            "file_id": entity.get("file_id", ""),
                            "source_ref": source_ref,
                            "block": block_name,
                            "layer": entity.get("layer", ""),
                            "matching_strategy": "source_ref+block+ordinal",
                            "match_ordinal": ordinal,
                        }
                        if ordinal >= len(mleader_objects):
                            rows.append(
                                {
                                    **base_row,
                                    "status": "error",
                                    "error": "В исходном чертеже меньше MULTILEADER, чем в БД для этого блока.",
                                }
                            )
                            continue

                        mleader = mleader_objects[ordinal]
                        annotation_text = get_mleader_annotation_text(mleader)
                        target_point = get_mleader_target_point(mleader)
                        matched_row = {
                            **base_row,
                            "annotation_text": annotation_text,
                        }
                        if target_point is None:
                            rows.append(
                                {
                                    **matched_row,
                                    "status": "error",
                                    "error": "Не удалось извлечь точку стрелки MULTILEADER.",
                                }
                            )
                            continue

                        nearest_entity, distance = find_closest_entity_in_entities(
                            target_point,
                            layout,
                            search_types=search_types,
                        )
                        if nearest_entity is None or distance == float("inf"):
                            rows.append(
                                {
                                    **matched_row,
                                    "status": "error",
                                    "target_point": _format_point_payload(target_point),
                                    "error": "Ближайшая сущность не найдена.",
                                }
                            )
                            continue

                        nearest_text = ""
                        if nearest_entity.dxftype() == "TEXT" and nearest_entity.dxf.hasattr("text"):
                            nearest_text = str(nearest_entity.dxf.text)
                        elif nearest_entity.dxftype() == "MTEXT":
                            nearest_text = DXFAnalyzer.get_text(nearest_entity)

                        rows.append(
                            {
                                **matched_row,
                                "status": "ok",
                                "target_point": _format_point_payload(target_point),
                                "nearest_type": str(nearest_entity.dxftype()),
                                "nearest_handle": (
                                    str(nearest_entity.dxf.handle)
                                    if nearest_entity.dxf.hasattr("handle")
                                    else ""
                                ),
                                "nearest_layer": str(getattr(nearest_entity.dxf, "layer", "") or ""),
                                "nearest_text": nearest_text,
                                "distance": round(float(distance), 6),
                            }
                        )
        except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
            for entity in source_entities:
                rows.append(
                    {
                        "status": "error",
                        "entity_id": entity["id"],
                        "file_id": entity.get("file_id", ""),
                        "source_ref": source_ref,
                        "block": entity.get("block", ""),
                        "layer": entity.get("layer", ""),
                        "matching_strategy": "source_ref+block+ordinal",
                        "error": str(exc),
                    }
                )

    return rows


def handle_find_mleader_nearest_command(
    file_ref: str | None = None,
    by_path: bool = False,
    search_types: list[str] | None = None,
) -> int:
    """Find nearest objects for MULTILEADER entities from the DB."""

    from .db import get_file_id_by_source, list_multileaders_for_nearest_lookup

    resolved_file_id = file_ref
    if file_ref is not None and by_path:
        resolved_file_id = asyncio.run(get_file_id_by_source(file_ref))
        if not resolved_file_id:
            out("Файл не найден в БД.")
            return constants.NOT_FOUND

    try:
        entities = asyncio.run(list_multileaders_for_nearest_lookup(file_id=resolved_file_id))
    except (LookupError, OSError, RuntimeError, ValueError) as e:
        logger.error("Ошибка чтения MULTILEADER из БД: %s", e)
        return constants.ERROR

    if not entities:
        out("Нет сущностей MULTILEADER для обработки.")
        return constants.OK

    normalized_search_types = tuple(search_types) if search_types else (
        "LINE",
        "CIRCLE",
        "LWPOLYLINE",
        "POLYLINE",
        "INSERT",
        "TEXT",
        "MTEXT",
    )
    rows = _collect_mleader_nearest_rows(entities, search_types=normalized_search_types)
    out(json.dumps(rows, ensure_ascii=False, indent=2))
    return constants.OK


def handle_project_add_command(
    name: str,
    description: str | None,
    created_by: str | None,
) -> int:
    """Create a project."""
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
    """Update a project."""
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
    """Delete a project with confirmation."""
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


def handle_category_add_command(
    name: str,
    description: str | None,
    parent_id: str | None,
) -> int:
    """Create a category."""
    from .db import create_category

    category = asyncio.run(
        create_category(name=name, description=description, parent_id=parent_id)
    )
    out(f"Категория создана: {category['id']}")
    out(f"Название: {category['name']}")
    if category["parent_id"]:
        out(f"Родитель: {category['parent_id']}")
    return constants.OK


def handle_category_update_command(
    category_id: str,
    name: str | None,
    description: str | None,
    parent_id: str | None,
) -> int:
    """Update a category."""
    from .db import update_category

    category = asyncio.run(
        update_category(
            category_id=category_id,
            name=name,
            description=description,
            parent_id=parent_id,
        )
    )
    if category is None:
        out("Категория не найдена.")
        return constants.NOT_FOUND

    out(f"Категория обновлена: {category['id']}")
    out(f"Название: {category['name']}")
    if category["parent_id"]:
        out(f"Родитель: {category['parent_id']}")
    return constants.OK


def handle_category_delete_command(category_id: str, yes: bool) -> int:
    """Delete a category with confirmation."""
    from .db import delete_category

    if not yes:
        answer = input(
            f"Удалить категорию {category_id}? Введите YES для подтверждения: "
        ).strip()
        if answer != "YES":
            out("Удаление отменено.")
            return constants.ERROR

    deleted = asyncio.run(delete_category(category_id=category_id))
    if not deleted:
        out("Категория не найдена.")
        return constants.NOT_FOUND

    out(f"Категория удалена: {category_id}")
    return constants.OK


def handle_category_list_command(parent_id: str | None) -> int:
    """Show the category list."""
    from .db import list_categories

    rows: list[ResultRow] = []
    for row in asyncio.run(list_categories(parent_id=parent_id)):
        rows.append(
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "parent_id": row["parent_id"],
            }
        )
    if not rows:
        out("Нет категорий.")
        return constants.OK

    print_as_table(rows)
    return constants.OK


def handle_file_stat_from_db_command(
    file_ref: str,
    by_path: bool,
    output_path: Path | None,
) -> int:
    """Collect XLSX statistics for a file already loaded into the DB."""

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
                        Entity.data["source_ref"].astext == file_ref,
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


def handle_export_blocks_xlsx_command(
    file_ref: str,
    by_path: bool,
    output_path: Path | None,
) -> int:
    """Export a summary table of file blocks from the DB to XLSX."""

    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    block_rows = _collect_block_export_rows(file_ref=file_ref, by_path=by_path, multiline=True)
    if block_rows is None:
        return constants.ERROR

    if output_path is None:
        if by_path:
            output_path = Path(file_ref).with_suffix(".blocks.xlsx")
        else:
            output_path = Path(f"{file_ref}_blocks.xlsx")

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Блоки"

    headers = [
        "Название блока",
        "Названия связанных слоев",
        "Интерпретация полная",
        "Полезные атрибуты",
        "Интерпретация краткая",
        "Количество вхождений блока в чертеж",
    ]
    ws.append(headers)

    fill = PatternFill(fill_type="solid", fgColor="D9D9D9")
    font = Font(bold=True)
    for cell in ws[1]:
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(wrap_text=True, vertical="top")

    for row in block_rows:
        ws.append([row[column] for column in headers])

    ws.freeze_panes = "A2"
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for col_idx, col_cells in enumerate(ws.iter_cols(), start=1):
        values = [str(cell.value) for cell in col_cells if cell.value is not None]
        width = max((len(line) for value in values for line in value.splitlines()), default=10)
        ws.column_dimensions[get_column_letter(col_idx)].width = min(width + 2, 60)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    out(f"XLSX по блокам сохранён: {output_path}")
    return constants.OK


def _collect_block_export_rows(
    file_ref: str,
    by_path: bool,
    multiline: bool,
) -> list[ResultRow] | None:
    from .db import get_file_id_by_source, list_blocks_for_export

    file_id = file_ref
    if by_path:
        file_id = asyncio.run(get_file_id_by_source(file_ref)) or ""
        if not file_id:
            out("Ошибка: file-сущность не найдена")
            return None

    try:
        blocks = asyncio.run(list_blocks_for_export(file_id))
    except (LookupError, OSError, ValueError) as exc:
        logger.error("Не удалось собрать данные блоков для экспорта: %s", exc)
        return None

    line_separator = "\n" if multiline else "; "
    text_separator = "\n" if multiline else " "
    rows: list[ResultRow] = []
    for block in blocks:
        raw_layers = block.get("layers", [])
        layers = raw_layers if isinstance(raw_layers, list) else []
        layer_names = line_separator.join(
            str(layer.get("name", ""))
            for layer in layers
            if isinstance(layer, dict) and str(layer.get("name", "")).strip()
        )
        attributes = block.get("attributes", {})
        formatted_attributes = (
            line_separator.join(f"{key}: {attributes[key]}" for key in sorted(attributes))
            if isinstance(attributes, dict)
            else ""
        )
        full_interpretation = str(block.get("full_interpretation", "") or "")
        if not multiline:
            full_interpretation = " ".join(full_interpretation.split())
        raw_insert_count = block.get("insert_count", 0)
        insert_count = raw_insert_count if isinstance(raw_insert_count, int) else 0

        rows.append(
            {
                "Название блока": str(block.get("name", "") or ""),
                "Названия связанных слоев": layer_names,
                "Интерпретация полная": full_interpretation.replace("\n", text_separator),
                "Полезные атрибуты": formatted_attributes,
                "Интерпретация краткая": str(block.get("short_interpretation", "") or ""),
                "Количество вхождений блока в чертеж": insert_count,
            }
        )
    return rows


def handle_export_blocks_table_command(
    file_ref: str,
    by_path: bool,
    output_path: Path | None,
) -> int:
    """Print a summary text table of file blocks from the DB."""
    block_rows = _collect_block_export_rows(file_ref=file_ref, by_path=by_path, multiline=False)
    if block_rows is None:
        return constants.ERROR
    if not block_rows:
        out("Нет блоков для экспорта.")
        return constants.OK

    table_text = as_table(block_rows)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(table_text + "\n", encoding="utf-8")
        out(f"Текстовая таблица по блокам сохранена: {output_path}")
        return constants.OK

    out(table_text)
    return constants.OK


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""

    parser = build_args_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(argv)

    return_code: int = 0
    match args.command:

        case "process":
            return_code = handle_process_command(
                Path(args.path),
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
                with_scores=args.with_scores,
            )

        case "extract-name-meaning":
            return_code = handle_extract_name_meaning_command(
                name=args.name,
                entity_id=args.entity_id,
                extra_context=args.extra_context,
                ai_model=args.ai_model,
                ai_base_url=args.ai_base_url,
                ai_api_key=args.ai_api_key,
            )

        case "explain-block":
            return_code = handle_explain_block_command(
                block_id=args.block_id,
                extra_context=args.extra_context,
                ai_model=args.ai_model,
                ai_base_url=args.ai_base_url,
                ai_api_key=args.ai_api_key,
            )

        case "categorize-entities":
            return_code = handle_categorize_entities_command(
                entity_ids=args.entity_ids,
                entity_type=args.entity_type,
                ai_model=args.ai_model,
                ai_base_url=args.ai_base_url,
                ai_api_key=args.ai_api_key,
                workers=args.workers,
                dry=args.dry,
            )

        case "interpret-entities":
            return_code = handle_interpret_entities_command(
                entity_ids=args.entity_ids,
                entity_type=args.entity_type,
                extra_context=args.extra_context,
                ai_model=args.ai_model,
                ai_base_url=args.ai_base_url,
                ai_api_key=args.ai_api_key,
                workers=args.workers,
                dry=args.dry,
            )

        case "interpret-blocks":
            return_code = handle_interpret_blocks_command(
                block_ids=args.block_ids,
                file_ref=args.file_ref,
                by_path=args.by_path,
                extra_context=args.extra_context,
                ai_model=args.ai_model,
                ai_base_url=args.ai_base_url,
                ai_api_key=args.ai_api_key,
                workers=args.workers,
                dry=args.dry,
            )

        case "interpret-block":
            return_code = handle_interpret_blocks_command(
                block_ids=[args.entity_id],
                file_ref=None,
                by_path=False,
                extra_context=args.extra_context,
                ai_model=args.ai_model,
                ai_base_url=args.ai_base_url,
                ai_api_key=args.ai_api_key,
                workers=1,
                dry=args.dry,
            )

        case "find-mleader-nearest":
            return_code = handle_find_mleader_nearest_command(
                file_ref=args.file_ref,
                by_path=args.by_path,
                search_types=args.search_types,
            )

        case "verify-extraction":
            return_code = handle_verify_extraction_command(
                drawing_path=Path(args.drawing),
                file_id=args.file_id,
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

        case "category-add":
            return_code = handle_category_add_command(
                name=args.name,
                description=args.description,
                parent_id=args.parent_id,
            )

        case "category-update":
            return_code = handle_category_update_command(
                category_id=args.category_id,
                name=args.name,
                description=args.description,
                parent_id=args.parent_id,
            )

        case "category-delete":
            return_code = handle_category_delete_command(
                category_id=args.category_id,
                yes=args.yes,
            )

        case "category-list":
            return_code = handle_category_list_command(parent_id=args.parent_id)

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

        case "export-block-png":
            return_code = handle_export_block_png_command(
                drawing_path=Path(args.drawing),
                block_name=args.block_name,
                output_path=Path(args.output) if args.output else None,
                dpi=args.dpi,
            )

        case "export-block-svg":
            return_code = handle_export_block_svg_command(
                drawing_path=Path(args.drawing),
                block_name=args.block_name,
                output_path=Path(args.output) if args.output else None,
            )

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

        case "export-blocks-xlsx":
            return_code = handle_export_blocks_xlsx_command(
                file_ref=args.file_ref,
                by_path=args.by_path,
                output_path=Path(args.output) if args.output else None,
            )

        case "export-blocks-table":
            return_code = handle_export_blocks_table_command(
                file_ref=args.file_ref,
                by_path=args.by_path,
                output_path=Path(args.output) if args.output else None,
            )


    return return_code


__all__ = ["DXFExplorer", "main"]
