"""Handler for the `parse` command."""

import logging

from pathlib import Path

from gettext import gettext as _

from src.parsedwg import constants, errors
from src.parsedwg.utils import display
from src.parsedwg.process_drawing import DrawingProcessor

logger = logging.getLogger(__name__)


def handle_parse_command(
    source_path: Path,
    project_name: str | None,
    dry: bool = False,
    detail_level: str = "high",
) -> int:
    """Scan DWG/DXF input, store the entity tree, and link it to a project."""

    try:
        summary = DrawingProcessor.parse_drawing_sources(
            source_path,
            project_name=project_name,
            dry=dry,
            detail_level=detail_level,
        )
    except errors.FileNotFound as e:
        logger.error(_("File not found: %s"), e, exc_info=True)
        return constants.ERROR

    except errors.ObjectNotFound as e:
        logger.error(_("Object not found: %s"), e, exc_info=True)
        return constants.ERROR

    except errors.UnsupportedFileType as e:
        logger.error(_("Unsupported file type: %s"), e, exc_info=True)
        return constants.ERROR
    
    display(_("Files found: {file_count}").format(**summary))
    display(_("Processing mode: {mode}").format(**summary))
    display(_("Entities created in DB: {created_entities}").format(**summary))

    return constants.OK

