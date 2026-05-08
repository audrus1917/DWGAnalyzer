"""Обработчик для команды `process`."""

import logging

from pathlib import Path

from src.parsedwg.process_source import process_source

from src.parsedwg import constants

logger = logging.getLogger(__name__)


def handle_process_command(
    source_path: Path,
    project_name: str | None = None,
) -> int:
    """Сканирует DWG/DXF, сохраняет дерево сущностей в БД и привязывает его к проекту."""

    try:
        summary = process_source(
            source_path,
            project_name=project_name,
        )
    except ValueError as e:
        logger.exception("Ошибка при обработке каталога / файла: %s", e)
        return constants.ERROR

    except RuntimeError as e:
        logger.error("Ошибка AI-режима: %s", e)
        return constants.ERROR
    print(f"Найдено файлов: {summary['file_count']}")
    # print(f"Обработано файлов: {summary['processed_count']}")
    print(f"Режим обработки: {summary['mode']}")
    print(f"Создано сущностей в БД: {summary['created_entities']}")
    return constants.OK

