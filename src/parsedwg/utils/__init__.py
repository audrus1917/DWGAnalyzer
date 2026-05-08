"""Вспомогательные утилиты."""

import sys
import json

from pathlib import Path

from typing import Any

import logging
import multiprocessing as mp

from src.parsedwg.constants import ResultRow


logger = logging.getLogger(__name__)


def get_workers_number(requested_workers: int) -> int:
    """Возвращает оптимальное число рабочих процессов для конвертации.

    Значение зависит от ресурсов машины и запрошенного числа workers.
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


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_table(rows: list[ResultRow]) -> str:
    """Форматирует строки результата в простую ASCII-таблицу."""

    if not rows:
        return "Нет данных."

    columns = list(rows[0].keys())
    prepared_rows = [[str(row.get(column, "")) for column in columns] for row in rows]
    widths = {
        column: max(len(column), *(len(values[index]) for values in prepared_rows))
        for index, column in enumerate(columns)
    }

    header = " | ".join(column.ljust(widths[column]) for column in columns)
    separator = "-+-".join("-" * widths[column] for column in columns)
    body = [
        " | ".join(values[index].ljust(widths[column]) for index, column in enumerate(columns))
        for values in prepared_rows
    ]
    return "\n".join([header, separator, *body])


def print_as_table(rows: list[ResultRow]) -> None:
    """Печатает строки результата в виде таблицы."""

    print(as_table(rows))


def _write_progress_line(message: str, previous_width: int = 0) -> int:
    """Обновляет одну строку прогресса в stdout."""

    width = max(previous_width, len(message))
    sys.stdout.write("\r" + message.ljust(width))
    sys.stdout.flush()
    return width


def _finish_progress_line(width: int) -> None:
    """Завершает строку прогресса переводом строки."""

    if width <= 0:
        return
    sys.stdout.write("\n")
    sys.stdout.flush()


def _format_duration_seconds(duration_seconds: float) -> str:
    """Форматирует длительность обработки в секундах."""

    return f"{duration_seconds:.2f} c"

def _save_rows_to_json(output_path: Path, rows: list[ResultRow]) -> None:
    """Сохраняет строки результата в JSON-файл."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _save_payload_to_json(output_path: Path, payload: object) -> None:
    """Сохраняет любой JSON-сериализуемый payload в файл."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
