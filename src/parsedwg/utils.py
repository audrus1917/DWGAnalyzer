"""Набор утилит."""

import argparse
import logging
import multiprocessing as mp

logger = logging.getLogger(__name__)


def get_workers_number(requested_workers: int) -> int:
    """Возвращает оптимальное количество рабочих процессов для конвертации, учитывая возможности
    машины и запрошенное значение."""

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
    """Строит и возвращает парсер аргументов командной строки."""

    list_common = argparse.ArgumentParser(add_help=False)
    list_common.add_argument("path", help="Путь к DWG/DXF файлу или каталогу")
    list_common.add_argument(
        "-o",
        "--output",
        help="Путь к JSON-файлу для одного входного файла или каталогу для пакетной обработки.",
    )

    extract_common = argparse.ArgumentParser(add_help=False)
    extract_common.add_argument("drawing", help="Путь к DWG или DXF файлу")

    parser = argparse.ArgumentParser(
        prog="parsedwg",
        description="Работа с DWG/DXF: получение данных и выполнение операций",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "list-layouts",
        parents=[list_common],
        help="Показать доступные layout'ы в DWG/DXF файле или каталоге.",
    )
    subparsers.add_parser(
        "list-blocks",
        parents=[list_common],
        help="Показать доступные блоки в DWG/DXF файле или каталоге.",
    )
    extract_block_parser = subparsers.add_parser(
        "extract-block",
        parents=[extract_common],
        help="Извлечь блок в отдельные файл.",
    )
    extract_block_parser.add_argument("block_name", help="Имя блока для извлечения")

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
        "--workers",
        type=int,
        default=0,
        help=(
            "Количество процессов для этапа обработки файлов "
            "(<=0: авторасчет по CPU)."
        ),
    )
    process_tree_parser.add_argument(
        "--ai-name-tags",
        action="store_true",
        help="Включить извлечение тегов из текстов через LangChain (опционально).",
    )
    process_tree_parser.add_argument(
        "--ai-model",
        default="llama3.1:8b",
        help="Имя модели для AI-режима (по умолчанию: llama3.1:8b).",
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
