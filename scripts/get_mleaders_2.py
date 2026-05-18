#!/usr/bin/env python

import sys

import logging
import argparse

from pathlib import Path as FilePath

import ezdxf
import json


logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def process_mleaders(dxf_path):
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    for mleader in msp.query("MULTILEADER"):# Получаем контекст данных выноски
        context = mleader.context

        insert_point = context.base_point

        logger.debug(
            "Точка вставки MULTILEADER: X=%s, Y=%s, Z=%s",
            insert_point.x,
            insert_point.y,
            insert_point.z,
        )
        entity_text = mleader.get_mtext_content() if hasattr(mleader, "get_mtext_content") else ""
        logger.debug(f"Обрабатываем MULTILEADER с текстом: '{entity_text}'")
        # Перебираем все группы линий (Leader Groups)
        for leader in context.leaders:

            # Перебираем отдельные линии выноски (Leader Lines)
            for line in leader.lines:
                # Получаем список всех вершин данной линии
                vertices = line.vertices
                logger.debug(f"Линия выноски содержит {len(vertices)} вершин:")
                for v in vertices:
                    logger.debug(f"  Координаты точки: X={v.x}, Y={v.y}, Z={v.z}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dxf_file", help="Путь к DWG/DXF файлу для извлечения данных")

    args = parser.parse_args()
    dxf_file = FilePath(args.dxf_file)
    if not dxf_file.is_file():
        logger.error(f"Файл '{dxf_file}' не найден.")
        sys.exit(1)

    process_mleaders(dxf_file)
