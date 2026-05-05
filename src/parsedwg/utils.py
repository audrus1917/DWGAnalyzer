"""Utility helpers."""

from typing import Any

import argparse
import logging
import multiprocessing as mp
import re

logger = logging.getLogger(__name__)


def get_workers_number(requested_workers: int) -> int:
    """Return the optimal number of worker processes for conversion.

    The value depends on machine capacity and the requested worker count.
    """

    logical_cpus = max(1, mp.cpu_count())
    max_workers = max(1, logical_cpus - 1)
    auto_workers = max(1, min(max_workers, int(logical_cpus * 0.7)))

    if requested_workers <= 0:
        logger.info(
            "Автовыбор workers: logical_cpus=%s, conversion_workers=%s",
            logical_cpus,
            auto_workers,
        )
        return auto_workers

    if requested_workers > max_workers:
        logger.warning(
            "Запрошено workers=%s, ограничено до %s (logical_cpus=%s).",
            requested_workers,
            max_workers,
            logical_cpus,
        )
        return max_workers

    return requested_workers


def build_args_parser() -> argparse.ArgumentParser:
    """Build and return the command-line argument parser."""

    extract_common = argparse.ArgumentParser(add_help=False)
    extract_common.add_argument("drawing", help="Путь к DWG или DXF файлу")

    parser = argparse.ArgumentParser(
        prog="parsedwg",
        description="Работа с DWG/DXF: получение данных и выполнение операций",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_block_parser = subparsers.add_parser(
        "extract-block",
        parents=[extract_common],
        help="Извлечь блок в отдельные файл.",
    )
    extract_block_parser.add_argument("block_name", help="Имя блока для извлечения")

    describe_block_parser = subparsers.add_parser(
        "describe-block",
        parents=[extract_common],
        help="Прочитать файл и вывести описание блока по имени.",
    )
    describe_block_parser.add_argument("block_name", help="Имя блока для описания")
    describe_block_parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Путь к JSON-файлу результата (если не указан, вывод в stdout).",
    )

    export_block_png_parser = subparsers.add_parser(
        "export-block-png",
        parents=[extract_common],
        help="Экспортировать выбранный блок в PNG.",
    )
    export_block_png_parser.add_argument("block_name", help="Имя блока для экспорта")
    export_block_png_parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Путь к PNG-файлу результата (по умолчанию: рядом с исходным файлом).",
    )
    export_block_png_parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Разрешение PNG в DPI (по умолчанию: 300).",
    )

    export_block_svg_parser = subparsers.add_parser(
        "export-block-svg",
        parents=[extract_common],
        help="Экспортировать выбранный блок в SVG.",
    )
    export_block_svg_parser.add_argument("block_name", help="Имя блока для экспорта")
    export_block_svg_parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Путь к SVG-файлу результата (по умолчанию: рядом с исходным файлом).",
    )

    export_block_dxf_parser = subparsers.add_parser(
        "export-block-dxf",
        parents=[extract_common],
        help="Вывести DXF-текст выбранного блока.",
    )
    export_block_dxf_parser.add_argument("block_name", help="Имя блока для экспорта")
    export_block_dxf_parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Путь к DXF-файлу результата (если не указан, вывод в stdout).",
    )

    file_stat_parser = subparsers.add_parser(
        "file-stat",
        parents=[extract_common],
        help="Собрать статистику по DXF/DWG файлу и сохранить в XLSX.",
    )
    file_stat_parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Путь к XLSX-файлу результата (по умолчанию: рядом с исходным файлом).",
    )
    file_stat_parser.add_argument(
        "--project",
        default=None,
        help="Название проекта (опционально).",
    )
    file_stat_parser.add_argument(
        "--db-tables",
        action="store_true",
        help="Дополнительно выгрузить XLSX для блоков-таблиц из БД по source_ref файла.",
    )
    file_stat_parser.add_argument(
        "--db-tables-by-id",
        action="store_true",
        help="Выгрузить XLSX для блоков-таблиц из БД по file_id (UUID сущности файла).",
    )
    file_stat_db_parser = subparsers.add_parser(
        "file-stat-from-db",
        help="Собрать статистику по файлу из БД (по file_id или пути) и сохранить в XLSX.",
    )
    file_stat_db_parser.add_argument(
        "file_ref",
        help="UUID file-сущности или путь к файлу (если --by-path)",
    )
    file_stat_db_parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Путь к XLSX-файлу результата (по умолчанию: file_id.xlsx или <stem>.xlsx)",
    )
    file_stat_db_parser.add_argument(
        "--by-path",
        action="store_true",
        help="Искать file-сущность по пути, а не по UUID.",
    )

    export_blocks_xlsx_parser = subparsers.add_parser(
        "export-blocks-xlsx",
        help="Экспортировать сводную таблицу по блокам из БД в XLSX.",
    )
    export_blocks_xlsx_parser.add_argument(
        "file_ref",
        help="UUID file-сущности или путь к файлу (если --by-path).",
    )
    export_blocks_xlsx_parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Путь к XLSX-файлу результата.",
    )
    export_blocks_xlsx_parser.add_argument(
        "--by-path",
        action="store_true",
        help="Искать file-сущность по пути, а не по UUID.",
    )

    export_blocks_table_parser = subparsers.add_parser(
        "export-blocks-table",
        help="Вывести сводную таблицу по блокам из БД в текстовом виде.",
    )
    export_blocks_table_parser.add_argument(
        "file_ref",
        help="UUID file-сущности или путь к файлу (если --by-path).",
    )
    export_blocks_table_parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Путь к TXT-файлу результата. Если не указан, вывод в stdout.",
    )
    export_blocks_table_parser.add_argument(
        "--by-path",
        action="store_true",
        help="Искать file-сущность по пути, а не по UUID.",
    )

    process_tree_parser = subparsers.add_parser(
        "process",
        help=(
            "Обойти каталог рекурсивно, найти DWG/DXF (включая ZIP)"
            " и загрузить дерево блоков/layers в БД."
        ),
    )
    process_tree_parser.add_argument(
        "path",
        help="Путь к каталогу.",
    )
    process_tree_parser.add_argument(
        "--project-name",
        "-p",
        dest="project_name",
        default=None,
        help="Название проекта. По умолчанию: имя корневой папки.",
    )
    process_tree_parser.add_argument(
        "--project-description",
        dest="project_description",
        default=None,
        help="Описание проекта.",
    )
    process_tree_parser.add_argument(
        "--created-by",
        dest="created_by",
        default=None,
        help="Кто создал проект.",
    )
    process_tree_parser.add_argument(
        "--dry",
        action="store_true",
        help="Выполнить разбор файлов без сохранения результатов в БД.",
    )
    process_tree_parser.add_argument(
        "--ai-name-tags",
        action="store_true",
        help="Включить извлечение тегов из текстов через LangChain (опционально).",
    )
    process_tree_parser.add_argument(
        "--ai-model",
        default="llama3.2",
        help="Имя модели для AI-режима (по умолчанию: llama3.2).",
    )
    process_tree_parser.add_argument(
        "--ai-base-url",
        default="http://localhost:11434/v1",
        help="OpenAI-совместимый base URL для модели (по умолчанию: Ollama).",
    )
    process_tree_parser.add_argument(
        "--ai-api-key",
        default="ollama",
        help="API ключ для AI провайдера (для Ollama можно оставить по умолчанию).",
    )

    extract_name_tags_parser = subparsers.add_parser(
        "extract-name-tags",
        help="Рекурсивно извлечь смысловые теги из имен файлов и папок.",
    )
    extract_name_tags_parser.add_argument(
        "path",
        help="Путь к каталогу или файлу.",
    )
    extract_name_tags_parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Путь к JSON-файлу результата (если не указан, вывод в stdout).",
    )
    extract_name_tags_parser.add_argument(
        "--ai-name-tags",
        action="store_true",
        help="Дополнительно извлечь теги через LangChain (опционально).",
    )
    extract_name_tags_parser.add_argument(
        "--ai-model",
        default="llama3.1:8b",
        help="Имя модели для AI-режима (по умолчанию: llama3.1:8b).",
    )
    extract_name_tags_parser.add_argument(
        "--ai-base-url",
        default="http://localhost:11434/v1",
        help="OpenAI-совместимый base URL для модели (по умолчанию: Ollama).",
    )
    extract_name_tags_parser.add_argument(
        "--ai-api-key",
        default="ollama",
        help="API ключ для AI провайдера (для Ollama можно оставить по умолчанию).",
    )

    extract_token_tags_parser = subparsers.add_parser(
        "extract-token-tags",
        help="Извлечь JSON-словарь token -> meanings через LLM для списка токенов.",
    )
    extract_token_tags_parser.add_argument(
        "tokens",
        nargs="*",
        help="Список токенов, например: M_Doors M_Wall_Glass.",
    )
    extract_token_tags_parser.add_argument(
        "--drawing",
        default=None,
        help="Путь к DWG/DXF файлу. Если указан, токены берутся из имен слоев чертежа.",
    )
    extract_token_tags_parser.add_argument(
        "--ai-model",
        default="llama3.2",
        help="Имя модели для AI-режима (по умолчанию: llama3.2).",
    )
    extract_token_tags_parser.add_argument(
        "--ai-base-url",
        default="http://localhost:11434/v1",
        help="OpenAI-совместимый base URL для модели (по умолчанию: Ollama).",
    )
    extract_token_tags_parser.add_argument(
        "--ai-api-key",
        default="ollama",
        help="API ключ для AI провайдера (для Ollama можно оставить по умолчанию).",
    )
    extract_token_tags_parser.add_argument(
        "--with-scores",
        action="store_true",
        help="Вернуть для каждого смысла объект с полем meaning и score от 0 до 1.",
    )

    extract_name_meaning_parser = subparsers.add_parser(
        "extract-name-meaning",
        help="Извлечь через LLM короткие инженерные смыслы для одного названия.",
    )
    extract_name_meaning_parser.add_argument(
        "name",
        nargs="?",
        default=None,
        help="Название или короткий текст, смысл которого нужно определить.",
    )
    extract_name_meaning_parser.add_argument(
        "--entity-id",
        dest="entity_id",
        default=None,
        help="UUID сущности в БД. Если указан, имя будет взято из БД.",
    )
    extract_name_meaning_parser.add_argument(
        "--extra-context",
        default="",
        help="Дополнительный контекст для LLM, например тип проекта или раздел.",
    )
    extract_name_meaning_parser.add_argument(
        "--ai-model",
        default="llama3.1:8b",
        help="Имя модели для AI-режима (по умолчанию: llama3.1:8b).",
    )
    extract_name_meaning_parser.add_argument(
        "--ai-base-url",
        default="http://localhost:11434/v1",
        help="Ollama base URL, например http://localhost:11434/v1 или http://localhost:11434.",
    )
    extract_name_meaning_parser.add_argument(
        "--ai-api-key",
        default="ollama",
        help="API ключ для AI провайдера (для Ollama можно оставить по умолчанию).",
    )

    explain_block_parser = subparsers.add_parser(
        "explain-block",
        help="Разобрать смысл имени блока из БД по его UUID.",
    )
    explain_block_parser.add_argument(
        "block_id",
        help="UUID сущности блока в БД.",
    )
    explain_block_parser.add_argument(
        "--extra-context",
        default="",
        help="Дополнительный контекст для LLM, например тип проекта или раздел.",
    )
    explain_block_parser.add_argument(
        "--ai-model",
        default="llama3.1:8b",
        help="Имя модели для AI-режима (по умолчанию: llama3.1:8b).",
    )
    explain_block_parser.add_argument(
        "--ai-base-url",
        default="http://localhost:11434/v1",
        help="Ollama base URL, например http://localhost:11434/v1 или http://localhost:11434.",
    )
    explain_block_parser.add_argument(
        "--ai-api-key",
        default="ollama",
        help="API ключ для AI провайдера (для Ollama можно оставить по умолчанию).",
    )

    categorize_entities_parser = subparsers.add_parser(
        "categorize-entities",
        help="Извлечь AI-категорию для сущностей и привязать её в БД.",
    )
    categorize_entities_parser.add_argument(
        "--entity-id",
        dest="entity_ids",
        action="append",
        default=None,
        help="UUID сущности. Можно указывать несколько раз.",
    )
    categorize_entities_parser.add_argument(
        "--entity-type",
        dest="entity_type",
        default=None,
        help="Тип сущности из поля entity_type, например BLOCK.",
    )
    categorize_entities_parser.add_argument(
        "--ai-model",
        default="llama3.2",
        help="Имя модели для AI-режима (по умолчанию: llama3.2).",
    )
    categorize_entities_parser.add_argument(
        "--ai-base-url",
        default="http://localhost:11434/v1",
        help="OpenAI-совместимый base URL для модели (по умолчанию: Ollama).",
    )
    categorize_entities_parser.add_argument(
        "--ai-api-key",
        default="ollama",
        help="API ключ для AI провайдера (для Ollama можно оставить по умолчанию).",
    )
    categorize_entities_parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Число параллельных AI-запросов при категоризации (по умолчанию: 1).",
    )
    categorize_entities_parser.add_argument(
        "--dry",
        action="store_true",
        help="Не записывать результат в БД, а вывести JSON-предпросмотр категоризации.",
    )

    interpret_entities_parser = subparsers.add_parser(
        "interpret-entities",
        help="Запросить LLM-интерпретацию имён для всех сущностей типа и сохранить в short_interpretation.",
    )
    interpret_entities_parser.add_argument(
        "--entity-id",
        dest="entity_ids",
        action="append",
        default=None,
        help="UUID сущности. Можно указывать несколько раз.",
    )
    interpret_entities_parser.add_argument(
        "--entity-type",
        dest="entity_type",
        default=None,
        help="Тип сущности из поля entity_type, например BLOCK.",
    )
    interpret_entities_parser.add_argument(
        "--extra-context",
        dest="extra_context",
        default="",
        help="Дополнительный контекст для LLM (например, раздел проекта).",
    )
    interpret_entities_parser.add_argument(
        "--ai-model",
        default="llama3.1:8b",
        help="Имя модели (по умолчанию: llama3.1:8b).",
    )
    interpret_entities_parser.add_argument(
        "--ai-base-url",
        default="http://localhost:11434/v1",
        help="OpenAI-совместимый base URL для модели (по умолчанию: Ollama).",
    )
    interpret_entities_parser.add_argument(
        "--ai-api-key",
        default="ollama",
        help="API ключ для AI провайдера.",
    )
    interpret_entities_parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Число параллельных AI-запросов (по умолчанию: 1).",
    )
    interpret_entities_parser.add_argument(
        "--dry",
        action="store_true",
        help="Не сохранять в БД, вывести JSON-предпросмотр.",
    )

    interpret_blocks_parser = subparsers.add_parser(
        "interpret-blocks",
        help=(
            "Распознать смысл имени блока и сохранить его в short_interpretation, "
            "а полное описание блока сохранить в full_interpretation."
        ),
    )
    interpret_blocks_parser.add_argument(
        "--block-id",
        dest="block_ids",
        action="append",
        default=None,
        help="UUID блока. Можно указывать несколько раз.",
    )
    interpret_blocks_parser.add_argument(
        "file_ref",
        nargs="?",
        default=None,
        help="UUID file-сущности или путь к файлу (если --by-path).",
    )
    interpret_blocks_parser.add_argument(
        "--by-path",
        action="store_true",
        help="Искать file-сущность по пути, а не по UUID.",
    )
    interpret_blocks_parser.add_argument(
        "--extra-context",
        dest="extra_context",
        default="",
        help="Дополнительный контекст для LLM (например, раздел проекта).",
    )
    interpret_blocks_parser.add_argument(
        "--ai-model",
        default="llama3.1:8b",
        help="Имя модели (по умолчанию: llama3.1:8b).",
    )
    interpret_blocks_parser.add_argument(
        "--ai-base-url",
        default="http://localhost:11434/v1",
        help="OpenAI-совместимый base URL для модели (по умолчанию: Ollama).",
    )
    interpret_blocks_parser.add_argument(
        "--ai-api-key",
        default="ollama",
        help="API ключ для AI провайдера.",
    )
    interpret_blocks_parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Число параллельных AI-запросов (по умолчанию: 1).",
    )
    interpret_blocks_parser.add_argument(
        "--dry",
        action="store_true",
        help="Не сохранять в БД, вывести JSON-предпросмотр.",
    )

    interpret_block_parser = subparsers.add_parser(
        "interpret-block",
        help=(
            "Распознать смысл имени одного блока и сохранить его в short_interpretation, "
            "а полное описание блока сохранить в full_interpretation."
        ),
    )
    interpret_block_parser.add_argument(
        "--entity-id",
        dest="entity_id",
        required=True,
        help="UUID блока в БД.",
    )
    interpret_block_parser.add_argument(
        "--extra-context",
        dest="extra_context",
        default="",
        help="Дополнительный контекст для LLM (например, раздел проекта).",
    )
    interpret_block_parser.add_argument(
        "--ai-model",
        default="llama3.1:8b",
        help="Имя модели (по умолчанию: llama3.1:8b).",
    )
    interpret_block_parser.add_argument(
        "--ai-base-url",
        default="http://localhost:11434/v1",
        help="OpenAI-совместимый base URL для модели (по умолчанию: Ollama).",
    )
    interpret_block_parser.add_argument(
        "--ai-api-key",
        default="ollama",
        help="API ключ для AI провайдера.",
    )
    interpret_block_parser.add_argument(
        "--dry",
        action="store_true",
        help="Не сохранять в БД, вывести JSON-предпросмотр.",
    )

    find_mleader_nearest_parser = subparsers.add_parser(
        "find-mleader-nearest",
        help=(
            "Найти ближайшие объекты для MULTILEADER-сущностей из БД, "
            "используя исходные DWG/DXF файлы."
        ),
    )
    find_mleader_nearest_parser.add_argument(
        "file_ref",
        nargs="?",
        default=None,
        help="UUID file-сущности или путь к файлу (если --by-path).",
    )
    find_mleader_nearest_parser.add_argument(
        "--by-path",
        action="store_true",
        help="Искать file-сущность по пути, а не по UUID.",
    )
    find_mleader_nearest_parser.add_argument(
        "--search-type",
        dest="search_types",
        action="append",
        default=None,
        help="Тип сущности-кандидата для поиска. Можно указывать несколько раз.",
    )

    verify_extraction_parser = subparsers.add_parser(
        "verify-extraction",
        help="Сверить DWG/DXF файл с сущностями, записанными в текущую БД.",
    )
    verify_extraction_parser.add_argument(
        "drawing",
        help="Путь к DWG/DXF файлу.",
    )
    verify_extraction_parser.add_argument(
        "--file-id",
        dest="file_id",
        default=None,
        help="UUID file-сущности в БД. Если не указан, ищется по source_ref файла.",
    )

    project_add_parser = subparsers.add_parser(
        "project-add",
        help="Добавить проект.",
    )
    project_add_parser.add_argument("name", help="Название проекта.")
    project_add_parser.add_argument(
        "--description",
        dest="description",
        default=None,
        help="Описание проекта.",
    )
    project_add_parser.add_argument(
        "--created-by",
        dest="created_by",
        default=None,
        help="Кто создал проект.",
    )

    project_update_parser = subparsers.add_parser(
        "project-update",
        help="Изменить существующий проект.",
    )
    project_update_parser.add_argument("project_id", help="UUID проекта.")
    project_update_parser.add_argument("--name", dest="name", default=None, help="Новое название.")
    project_update_parser.add_argument(
        "--description",
        dest="description",
        default=None,
        help="Новое описание.",
    )
    project_update_parser.add_argument(
        "--created-by",
        dest="created_by",
        default=None,
        help="Новое значение created_by.",
    )

    project_delete_parser = subparsers.add_parser(
        "project-delete",
        help="Удалить проект.",
    )
    project_delete_parser.add_argument("project_id", help="UUID проекта.")
    project_delete_parser.add_argument(
        "--yes",
        action="store_true",
        help="Подтвердить удаление без интерактивного запроса.",
    )

    category_add_parser = subparsers.add_parser(
        "category-add",
        help="Добавить категорию.",
    )
    category_add_parser.add_argument("name", help="Название категории.")
    category_add_parser.add_argument(
        "--description",
        dest="description",
        default=None,
        help="Описание категории.",
    )
    category_add_parser.add_argument(
        "--parent-id",
        dest="parent_id",
        default=None,
        help="UUID родительской категории.",
    )

    category_update_parser = subparsers.add_parser(
        "category-update",
        help="Изменить существующую категорию.",
    )
    category_update_parser.add_argument("category_id", help="UUID категории.")
    category_update_parser.add_argument("--name", dest="name", default=None, help="Новое название.")
    category_update_parser.add_argument(
        "--description",
        dest="description",
        default=None,
        help="Новое описание.",
    )
    category_update_parser.add_argument(
        "--parent-id",
        dest="parent_id",
        default=None,
        help="UUID новой родительской категории.",
    )

    category_delete_parser = subparsers.add_parser(
        "category-delete",
        help="Удалить категорию.",
    )
    category_delete_parser.add_argument("category_id", help="UUID категории.")
    category_delete_parser.add_argument(
        "--yes",
        action="store_true",
        help="Подтвердить удаление без интерактивного запроса.",
    )

    category_list_parser = subparsers.add_parser(
        "category-list",
        help="Показать список категорий.",
    )
    category_list_parser.add_argument(
        "--parent-id",
        dest="parent_id",
        default=None,
        help="Вернуть только прямых потомков указанной категории.",
    )

    ingest_docs_parser = subparsers.add_parser(
        "ingest-docs",
        help="Рекурсивно найти PDF/DOCX/XLSX/CSV и загрузить в БД для RAG.",
    )
    ingest_docs_parser.add_argument(
        "path",
        help="Путь к файлу или каталогу для рекурсивного обхода.",
    )

    search_parser = subparsers.add_parser(
        "search",
        help="Полнотекстовый поиск сущностей в БД PostgreSQL.",
    )
    search_parser.add_argument("query", help="Поисковый запрос.")
    search_parser.add_argument(
        "--type",
        dest="type",
        choices=["folder", "file", "zipfile", "zipped_file", "block", "layout", "layer", "primitive"],
        help="Фильтр по типу сущности.",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Максимальное число результатов (по умолчанию: 20).",
    )
    search_parser.add_argument(
        "--parent-id",
        dest="parent_id",
        default=None,
        help="Фильтр по parent_id: вернуть только прямых потомков этого UUID.",
    )
    search_parser.add_argument(
        "-o",
        "--output",
        help="Путь к JSON-файлу для сохранения результатов.",
    )

    _entity_type_choices = [
        "folder", "file", "zipfile", "zipped_file", "block", "layout", "layer", "primitive"
    ]

    index_parser = subparsers.add_parser(
        "index",
        help="Создать/обновить эмбеддинги для сущностей в БД (nomic-embed-text).",
    )
    index_parser.add_argument(
        "--type",
        dest="type",
        choices=_entity_type_choices,
        help="Индексировать только указанный тип сущностей.",
    )
    index_parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        dest="batch_size",
        help="Размер батча запросов к Ollama (по умолчанию: 50).",
    )
    index_parser.add_argument(
        "--reindex",
        action="store_true",
        help="Пересоздать эмбеддинги, даже если они уже есть.",
    )

    ask_parser = subparsers.add_parser(
        "ask",
        help="RAG-запрос: векторный поиск + генерация ответа через llama3.2.",
    )
    ask_parser.add_argument("question", help="Вопрос на естественном языке.")
    ask_parser.add_argument(
        "--type",
        dest="type",
        choices=_entity_type_choices,
        help="Фильтр по типу сущности.",
    )
    ask_parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        dest="top_k",
        help="Число ближайших источников для контекста (по умолчанию: 5).",
    )
    ask_parser.add_argument(
        "-o",
        "--output",
        help="Путь к JSON-файлу для сохранения ответа и источников.",
    )

    return parser


class CustomFormatter(logging.Formatter):
    """Log formatter that changes the message shape by log level."""

    FORMATS = {
        logging.DEBUG: "[DEBUG] %(name)s: %(message)s",
        logging.INFO: "%(message)s",
        logging.WARNING: "WARNING: %(message)s (%(filename)s:%(lineno)d)",
        logging.ERROR: "ERROR!!! %(asctime)s - %(message)s",
        logging.CRITICAL: "CRITICAL FAILURE: %(message)s"
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, "%(levelname)s: %(message)s")
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)
    

def out(value: Any) -> None:
    """Write a value to stdout.

    Alias for :func:`print` to keep call sites distinct from temporary debugging.
    """

    print(value)


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


import ezdxf
from ezdxf.math import Vec3

def get_mleader_target_point(mleader):
    """Extract the point targeted by the first leader arrow."""
    try:
        # MLeader may have multiple leaders; use the first one.
        context = mleader.context
        leader = context.leaders[0]
        line = leader.lines[0]
        # The arrow tip is the first or last vertex, depending on the type.
        return line.vertices[0] 
    except (IndexError, AttributeError):
        return None


def get_mleader_annotation_text(mleader) -> str:
    """Return MULTILEADER annotation text, if present."""
    try:
        context = mleader.context
        mtext = getattr(context, "mtext", None)
        content = getattr(mtext, "default_content", "")
    except AttributeError:
        return ""

    text = str(content or "").strip()
    text = re.sub(r"\\P", " ", text)
    text = re.sub(r"\\[LOKlok]", "", text)
    text = re.sub(r"\\~", " ", text)

    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\{\\[^;{}]+;([^{}]*)\}", r"\1", text)

    text = re.sub(r"\\[A-Za-z][^;]*;", "", text)
    text = text.replace("{", "").replace("}", "")
    return " ".join(text.split())

def find_closest_entity(
    target_point,
    msp,
    search_types=('LINE', 'CIRCLE', 'LWPOLYLINE', 'POLYLINE', 'INSERT', 'TEXT', 'MTEXT'),
):
    """
    Find the nearest object of the requested types to the given point.
    
    .. code-block:: python

        # USAGE EXAMPLE:
        doc = ezdxf.readfile("your_file.dxf")
        msp = doc.modelspace()

        for ml in msp.query("MULTILEADER"):
            tip = get_mleader_target_point(ml)
            target, distance = find_closest_entity(tip, msp)
            
            if target and distance < 1.0: # Tolerance threshold.
                print(f"Leader '{ml.handle}' points to {target.dxftype()} ({target.handle})")
    """

    if not target_point:
        return None
    
    min_dist = float('inf')
    closest_entity = None
    
    for entity in msp.query('|'.join(search_types)):
        # Compute the distance from the point to the entity in a simplified way.
        # For exact curve distance, use .bbox() or .dist_to_entity() style methods.
        try:
            bbox = entity.bounding_box()
            dist = bbox.center.distance(target_point) # Rough estimate via center point.
            
            if dist < min_dist:
                min_dist = dist
                closest_entity = entity
        except Exception:
            continue
            
    return closest_entity, min_dist


def find_closest_entity_in_entities(
    target_point,
    entities,
    search_types=('LINE', 'CIRCLE', 'LWPOLYLINE', 'POLYLINE', 'INSERT', 'TEXT', 'MTEXT'),
):
    """Find the nearest entity within an already iterated DXF entity set."""

    if not target_point:
        return None, float('inf')

    normalized_types = {str(value).upper() for value in search_types}
    min_dist = float('inf')
    closest_entity = None

    for entity in entities:
        try:
            if str(entity.dxftype()).upper() not in normalized_types:
                continue
            bbox = entity.bounding_box()
            dist = bbox.center.distance(target_point)
            if dist < min_dist:
                min_dist = dist
                closest_entity = entity
        except Exception:
            continue

    return closest_entity, min_dist
