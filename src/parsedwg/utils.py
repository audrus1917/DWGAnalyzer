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
    extract_name_tags_parser = subparsers.add_parser(
        "extract-name-tags",
        help="Извлечь смысловые теги из имен файлов (рекурсивно для каталога).",
    )
    extract_name_tags_parser.add_argument("path", help="Путь к файлу или каталогу")
    extract_name_tags_parser.add_argument(
        "-o",
        "--output",
        help="Путь к JSON-файлу с результатами.",
    )

    process_tree_parser = subparsers.add_parser(
        "process",
        help=(
            "Обойти каталог рекурсивно, найти DWG (включая ZIP), сконвертировать"
            " в DXF и загрузить дерево блоков/layers в БД."
        ),
    )
    process_tree_parser.add_argument(
        "path",
        help="Путь к каталогу.",
    )
    process_tree_parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help=(
            "Количество процессов для этапа конвертации DWG в DXF "
            "(<=0: авторасчет по CPU)."
        ),
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

