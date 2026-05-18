"""Workers for agent pipeline steps."""

from __future__ import annotations

import time

from pathlib import Path

from . import constants


async def run_interpret_blocks_step(
    file_ref: str,
    by_path: bool,
    project_name: str | None,
    ai_model: str,
    ai_base_url: str,
    ai_api_key: str,
    workers: int,
    dry: bool,
) -> dict[str, object]:
    from .db import get_file_id_by_source
    from .ai_services import interpret_blocks

    started_at = time.perf_counter()
    file_id = file_ref if not by_path else await get_file_id_by_source(file_ref)
    if not file_id and project_name:
        from .commands.parse import handle_parse_command

        return_code = handle_parse_command(Path(file_ref), project_name=project_name)
        if return_code != constants.OK:
            raise RuntimeError(f"Failed to pre-process source: {file_ref}")
        file_id = await get_file_id_by_source(file_ref)

    if not file_id:
        raise LookupError(
            "file_id for block interpretation was not found. Load the file into the database "
            "first or pass --project for pre-processing."
        )

    result = await interpret_blocks(
        block_ids=None,
        file_ref=file_ref if by_path else str(file_id),
        by_path=by_path,
        extra_context="",
        ai_model=ai_model,
        ai_base_url=ai_base_url,
        ai_api_key=ai_api_key,
        workers=workers,
        dry=dry,
    )
    rows = result.get("rows", [])
    failures = result.get("failures", [])
    if not isinstance(rows, list) or not isinstance(failures, list):
        raise RuntimeError("interpret_blocks returned an invalid result.")
    if not rows and failures:
        raise RuntimeError("interpret_blocks failed.")

    return {
        "processed": len(rows) + len(failures),
        "failed": len(failures),
        "saved": len(rows),
        "file_id": str(file_id),
        "duration_seconds": round(time.perf_counter() - started_at, 3),
    }


async def run_categorize_entities_step(
    file_ref: str,
    by_path: bool,
    entity_type: str,
    ai_model: str,
    ai_base_url: str,
    ai_api_key: str,
    workers: int,
    dry: bool,
) -> dict[str, object]:
    from .ai_services import categorize_entities
    from .db import get_file_id_by_source

    started_at = time.perf_counter()
    file_id = file_ref if not by_path else await get_file_id_by_source(file_ref)
    if not file_id:
        raise LookupError(
            "file_id for categorization was not found. Load the file into the database first."
        )

    rows = await categorize_entities(
        entity_ids=None,
        entity_type=entity_type,
        ai_model=ai_model,
        ai_base_url=ai_base_url,
        ai_api_key=ai_api_key,
        workers=workers,
        dry=dry,
        file_id=str(file_id),
    )
    return {
        "processed": len(rows),
        "failed": 0,
        "saved": len(rows),
        "file_id": str(file_id),
        "entity_type": entity_type,
        "duration_seconds": round(time.perf_counter() - started_at, 3),
    }


async def run_verify_extraction_step(
    drawing_path: Path,
    file_id: str | None,
) -> dict[str, object]:
    from .verify_extraction import verify_extraction

    started_at = time.perf_counter()
    report = await verify_extraction(drawing_path, file_id=file_id)
    return {
        "ok": bool(report.get("ok")),
        "report": report,
        "duration_seconds": round(time.perf_counter() - started_at, 3),
    }