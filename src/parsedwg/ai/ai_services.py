"""Service layer for AI operations on entities and blocks."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, cast

from src.parsedwg.tags import AgentConfig, TagsExtractor
from src.parsedwg.settings import settings
from src.parsedwg.utils import _finish_progress_line, _format_duration_seconds, _write_progress_line


logger = logging.getLogger(__name__)

async def categorize_entities(
    entity_ids: list[str] | None,
    entity_type: str | None,
    ai_model: str,
    ai_base_url: str,
    ai_api_key: str,
    workers: int,
    dry: bool,
    file_id: str | None = None,
    extra_context: str = "construction, drawing",
) -> list[dict[str, object]]:
    """Extract semantic categories for entities and link them in the database."""

    from src.parsedwg.db import assign_semantic_category, list_entities

    if bool(entity_ids) == bool(entity_type):
        raise ValueError("Specify either entity_ids or entity_type.")
    if workers <= 0:
        raise ValueError("--workers must be greater than 0.")

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

    list_entities = cast(Any, list_entities)
    selected_entities = await list_entities(
        entity_ids=entity_ids,
        entity_type=entity_type,
        file_id=file_id,
    )
    if not selected_entities:
        return []
    if not dry:
        print(f"Selected entities: {len(selected_entities)}")

    extractor = TagsExtractor.from_config(
        AgentConfig(
            model=ai_model,
            base_url=ai_base_url,
            api_key=ai_api_key,
        )
    )

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
                        raise ValueError("Invalid entity payload in dry-run categorization mode.")
                    rows.append(_build_dry_row(entity_payload, normalized_meanings))
                    continue

                saved_row = await assign_semantic_category(
                    entity_id=str(item["entity_id"]),
                    meanings=normalized_meanings,
                )
                rows.append(saved_row)
                progress_width = _write_progress_line(
                    "Saved {current}/{total}: {entity_id} -> {category_name} [{status}]".format(
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


async def interpret_blocks(
    block_ids: list[str] | None,
    file_ref: str | None,
    by_path: bool,
    extra_context: str,
    ai_model: str,
    ai_base_url: str,
    ai_api_key: str,
    workers: int,
    dry: bool,
) -> dict[str, object]:
    """Interpret blocks and save short and full interpretations."""

    from src.parsedwg.db import (
        get_file_id_by_source,
        get_full_description,
        list_blocks_for_interpretation,
        save_block_description,
        save_block_interpretations,
    )
    from src.parsedwg.tags import get_name_meaning

    logger.debug("AI API key configured: %s", bool(ai_api_key))

    if bool(block_ids) == bool(file_ref):
        raise ValueError("Specify either block_ids or file_ref.")
    if workers <= 0:
        raise ValueError("--workers must be greater than 0.")

    resolved_file_id = file_ref
    if file_ref is not None and by_path:
        resolved_file_id = await get_file_id_by_source(file_ref)
        if not resolved_file_id:
            raise LookupError("File was not found in the database.")

    normalized_context = " ".join(extra_context.split())
    llm_timeout_seconds = settings.ai_timeout_seconds

    blocks = await list_blocks_for_interpretation(
        block_ids=block_ids,
        file_id=resolved_file_id,
    )
    if not blocks:
        return {"rows": [], "failures": []}
    if not dry:
        print(f"Selected blocks: {len(blocks)}")

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
                        get_name_meaning,
                        name=block_text_for_llm,
                        chat_url=ai_base_url,
                        model=ai_model,
                        extra_context=normalized_context,
                        timeout_seconds=llm_timeout_seconds,
                    ),
                    timeout=llm_timeout_seconds + 5.0,
                )
                full_description = await asyncio.wait_for(
                    asyncio.to_thread(
                        get_name_meaning,
                        name=block_text_for_llm,
                        chat_url=ai_base_url,
                        model=ai_model,
                        extra_context=(
                            normalized_context
                            + "\nProvide the most detailed possible description of this "
                            + "block's purpose and structure, including engineer-facing details."
                        ),
                        timeout_seconds=llm_timeout_seconds,
                    ),
                    timeout=llm_timeout_seconds + 10.0,
                )
                block_description = block_text_for_llm
                full_interpretation = full_description
            except TimeoutError:
                duration_seconds = round(time.perf_counter() - started_at, 3)
                return {
                    "status": "error",
                    "block_id": block_id,
                    "block_name": block_name,
                    "duration_seconds": duration_seconds,
                    "error": (
                        "Timed out while waiting for the LLM response for block "
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
                    "Block interpretation error for %s (%s) after %s: %s",
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
                        "Failed to save interpretation for block %s (%s): %s",
                        block_id or "-",
                        block_name or "-",
                        exc,
                    )

            if not dry:
                print(f"\nBlock {block_name or block_id or '-'} processed in {duration_label}")

            processed = len(rows) + len(failures)
            if not dry:
                progress_width = _write_progress_line(
                    "Processed {processed}/{total}: success {success}, errors {errors}".format(
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