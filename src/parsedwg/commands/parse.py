"""Handler for the `parse` command."""

import logging

from pathlib import Path

from src.parsedwg.process_drawing import parse_drawing

from src.parsedwg import constants, errors

logger = logging.getLogger(__name__)


def handle_parse_command(
    source_path: Path,
    project_name: str | None,
    dry: bool = False,
    detail_level: str = "high",
) -> int:
    """Scan DWG/DXF input, store the entity tree, and link it to a project."""

    try:
        summary = parse_drawing(
            source_path,
            project_name=project_name,
            dry=dry,
            detail_level=detail_level,
        )
    except errors.FileNotFound as e:
        logger.error("File not found: %s", e, exc_info=True)
        return constants.ERROR

    except errors.ObjectNotFound as e:
        logger.error("Object not found: %s", e, exc_info=True)
        return constants.ERROR

    except errors.UnsupportedFileType as e:
        logger.error("Unsupported file type: %s", e, exc_info=True)
        return constants.ERROR
    
    print(f"Files found: {summary['file_count']}")
    print(f"Processing mode: {summary['mode']}")
    print(f"Entities created in DB: {summary['created_entities']}")
    return constants.OK

