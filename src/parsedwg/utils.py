"""Набор утилит."""

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
