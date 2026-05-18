"""Handler for the `parse` command."""

import logging

from pathlib import Path

from src.parsedwg.process_source import parse_drawing

from src.parsedwg import constants

logger = logging.getLogger(__name__)


def handle_parse_command(
    source_path: Path,
    project_name: str | None,
    dry: bool = False,
    detail_level: str = "high",
) -> int:
    """Scan DWG/DXF input, store the entity tree, and link it to a project."""

    logger.debug("Start parsing command")
    try:
        summary = parse_drawing(
            source_path,
            project_name=project_name,
            dry=dry,
            detail_level=detail_level,
        )
    except ValueError as e:
        logger.exception("Failed to process directory or file: %s", e)
        return constants.ERROR

    except RuntimeError as e:
        logger.error("AI mode error: %s", e, exc_info=True)
        return constants.ERROR
    
    print(f"Files found: {summary['file_count']}")
    print(f"Processing mode: {summary['mode']}")
    print(f"Entities created in DB: {summary['created_entities']}")
    return constants.OK

