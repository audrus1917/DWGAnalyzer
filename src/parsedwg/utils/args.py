"""Утилиты для формирования парсера аргументов командной строки."""

import argparse
import logging

from src.parsedwg.settings import settings


logger = logging.getLogger(__name__)


def build_args_parser() -> argparse.ArgumentParser:
    """Возвращает парсер аргументов командной строки."""

    readfile_common = argparse.ArgumentParser(add_help=False)
    readfile_common.add_argument("file_path", help="Путь к DWG или DXF файлу")

    output_common = argparse.ArgumentParser(add_help=False)
    output_common.add_argument("-o", "--output", default=None, help="Файл для вывода")

    ai_common = argparse.ArgumentParser(add_help=False)
    ai_common.add_argument(
        "--ai-model",
        default=settings.ai_model,
        help="Имя модели для AI-режима (по умолчанию: llama3.1:8b).",
    )
    ai_common.add_argument(
        "--ai-base-url",
        default=settings.ai_base_url,
        help="OpenAI-совместимый base URL для модели (по умолчанию: Ollama).",
    )
    ai_common.add_argument(
        "--ai-api-key",
        default=settings.ai_api_key,
        help="API ключ для AI провайдера (для Ollama можно оставить по умолчанию).",
    )

    parser = argparse.ArgumentParser(
        prog="parsedwg",
        description="Работа с DWG/DXF: получение данных и выполнение операций",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_block_parser = subparsers.add_parser(
        "extract-block",
        parents=[readfile_common],
        help="Извлечь блок в отдельные файл.",
    )
    extract_block_parser.add_argument("block_name", help="Имя блока для извлечения")

    describe_block_parser = subparsers.add_parser(
        "describe-block",
        parents=[readfile_common, output_common],
        help="Прочитать файл и вывести описание блока по имени.",
    )
    describe_block_parser.add_argument("block_name", help="Имя блока для описания")

    export_block_parser = subparsers.add_parser(
        "export-block-png",
        parents=[readfile_common, output_common],
        help="Экспорт выбранного блока в (PNG, SVG, DXF).",
    )
    export_block_parser.add_argument("block_name", help="Имя блока для экспорта")
    export_block_parser.add_argument(
        "-f",
        "--format",
        default=None,
        help="Формат экспорта блока (PNG, SVG, DXF).",
    )

    process_parser = subparsers.add_parser(
        "process",
        help=(
            "Обойти каталог рекурсивно, найти DWG/DXF (включая ZIP)"
            " и загрузить дерево блоков/layers в БД."
        ),
    )
    process_parser.add_argument(
        "path",
        help="Путь к каталогу / файлу.",
    )
    process_parser.add_argument(
        "--project",
        "-p",
        type=str,
        dest="project",
        required=True,
        help="Название существующего проекта.",
    )

    extract_name_meaning_parser = subparsers.add_parser(
        "extract-name-meaning",
        parents=[ai_common],
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

    explain_block_parser = subparsers.add_parser(
        "explain-block",
        parents=[ai_common],
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

    categorize_entities_parser = subparsers.add_parser(
        "categorize-entities",
        parents=[ai_common],
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
        parents=[ai_common],
        help="Запросить LLM-интерпретацию имён для всех сущностей типа и сохранить её в entity_embedding.short_interpretation.",
    )
    interpret_entities_parser.add_argument(
        "--entity-id",
        dest="entity_ids",
        action="append",
        default=None,
        help="ID сущности. Можно указывать несколько раз.",
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
        parents=[ai_common],
        help=(
            "Распознать смысл имени блока и сохранить интерпретации в "
            "entity_embedding.short_interpretation и entity_embedding.full_interpretation."
        ),
    )
    interpret_blocks_parser.add_argument(
        "--block-id",
        dest="block_ids",
        action="append",
        default=None,
        help="ID блока. Можно указывать несколько раз.",
    )
    interpret_blocks_parser.add_argument(
        "file_ref",
        nargs="?",
        default=None,
        help="ID file-сущности или путь к файлу (если --by-path).",
    )
    interpret_blocks_parser.add_argument(
        "--by-path",
        action="store_true",
        help="Искать file-сущность по пути, а не по ID.",
    )
    interpret_blocks_parser.add_argument(
        "--extra-context",
        dest="extra_context",
        default="",
        help="Дополнительный контекст для LLM (например, раздел проекта).",
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
        parents=[ai_common],
        help=(
            "Распознать смысл имени одного блока и сохранить интерпретации в "
            "entity_embedding.short_interpretation и entity_embedding.full_interpretation."
        ),
    )
    interpret_block_parser.add_argument(
        "--entity-id",
        dest="entity_id",
        required=True,
        help="ID блока в БД.",
    )
    interpret_block_parser.add_argument(
        "--extra-context",
        dest="extra_context",
        default="",
        help="Дополнительный контекст для LLM (например, раздел проекта).",
    )
    interpret_block_parser.add_argument(
        "--dry",
        action="store_true",
        help="Не сохранять в БД, вывести JSON-предпросмотр.",
    )

    verify_extraction_parser = subparsers.add_parser(
        "verify-extraction",
        parents=[readfile_common],
        help="Сверить DWG/DXF файл с сущностями, записанными в текущую БД.",
    )
    verify_extraction_parser.add_argument(
        "--file-id",
        dest="file_id",
        default=None,
        help="UUID file-сущности в БД",
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

    export_interpreted_blocks_xlsx_parser = subparsers.add_parser(
        "export-interpreted-blocks-xlsx",
        parents=[output_common],
        help="Выгрузить в XLSX все блоки с непустой short_interpretation.",
    )

    return parser

