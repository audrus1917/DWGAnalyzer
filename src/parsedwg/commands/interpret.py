"""Handler for the `parse` command."""

import logging
import asyncio
import json

from gettext import gettext as _

from src.parsedwg import constants
from src.parsedwg.settings import settings
from src.parsedwg.utils import display
from src.parsedwg.db import list_entities, save_short_interpretation
from src.parsedwg.ai.tags import get_name_meaning
from src.parsedwg.utils import (
    _write_progress_line,
    _finish_progress_line,
)

logger = logging.getLogger(__name__)


def handle_interpret_command(
    entity_ids: list[str] | None,
    entity_type: str | None,
    workers: int = 1,
    dry: bool = False,
) -> int:
    """Request entity name interpretations from the LLM by id or type.

    Save the result into entity embedding interpretation fields.

    Args:
        entity_ids: Explicit list of entity identifiers to interpret.
        entity_type: Entity type to select if entity_ids are not provided.
        workers: Maximum number of parallel tasks.
        dry: If true, do not save the result to the database.

    Returns:
        CLI command exit code.

    Raises:
        RuntimeError: Can be raised by internal AI calls and converted to an error code.
        ValueError: Can be raised by internal selection, validation, or save calls and converted to an error code.
        LookupError: Can be raised by internal database calls and converted to an error code.
        TimeoutError: Can be raised by internal AI calls and converted to an error code.
    """

    display(_("Starting interpret command"))

    if bool(entity_ids) == bool(entity_type):
        logger.error("Specify either --entity-id or --entity-type.")
        return constants.UNBOUND_ERROR
    if workers <= 0:
        logger.error("--workers must be greater than 0.")
        return constants.UNBOUND_ERROR

    llm_timeout_seconds = settings.ai_timeout_seconds

    async def _run() -> dict[str, object]:
        entities = await list_entities(
            entity_ids=entity_ids,
            entity_type=entity_type,
        )
        if not entities:
            return {"rows": [], "failures": []}
        if not dry:
            print(f"Selected entities: {len(entities)}")

        semaphore = asyncio.Semaphore(workers)

        async def _process_entity(entity: dict[str, str]) -> dict[str, object]:
            extra_context = ""
            if "entity_type" in entity:
                entity_type_name = constants.ENTITY_TYPE_NAMES.get(entity["entity_type"], None)
                if entity_type_name:
                    extra_context = f"Тип примитива={entity_type_name}"
            async with semaphore:
                try:
                    text = await asyncio.wait_for(
                        asyncio.to_thread(
                            get_name_meaning,
                            name=entity["name"],
                            chat_url=settings.ai_base_url,
                            model=settings.ai_model,
                            extra_context=extra_context,
                            timeout_seconds=llm_timeout_seconds,
                        ),
                        timeout=llm_timeout_seconds + 5.0,
                    )
                except TimeoutError:
                    return {
                        "status": "error",
                        "entity_id": entity["id"],
                        "entity_name": entity["name"],
                        "error": (
                            "Timed out while waiting for the LLM response for entity "
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
                    "LLM response interpret-entities: entity_id=%s entity_name=%s\n%s",
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
        tasks = [asyncio.create_task(_process_entity(entity)) for entity in entities]
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
                        "Entity interpretation error for %s (%s): %s",
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
                                "Saving interpretation for entity %s (%s): %s",
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
                            "Failed to save interpretation for entity %s (%s): %s",
                            entity_id or "-",
                            entity_name or "-",
                            exc,
                        )

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
                logger.error("Failed to interpret any entities. Errors: %d", len(failures))
                return constants.ERROR
            print("No entities to interpret.")
            return constants.OK
        if dry:
            print(json.dumps(rows + failures, ensure_ascii=False, indent=2))
            return constants.OK
        print(f"Interpreted: {len(rows)}")
        if failures:
            print(f"Errors: {len(failures)}")
        return constants.OK
    except RuntimeError as e:
        logger.error("AI mode error: %s", e)
        return constants.ERROR
    except (LookupError, OSError, ValueError, TimeoutError) as e:
        logger.error("Entity interpretation failed: %s", e)
        return constants.UNBOUND_ERROR
