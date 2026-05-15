#!/usr/bin/env python

import sys

import logging
import argparse

from pathlib import Path

import ezdxf
from ezdxf.entities.dxfgfx import DXFGraphic
from ezdxf.math import Matrix44

from ezdxf.addons.geo import GeoProxy

import shapely.geometry
import shapely.validation


logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def convert_dxf(dxf_path):
    # 1. Чтение файла и пространств
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    projection_matrix = Matrix44.scale(1, 1, 0)
    # Выбираем все базовые графические примитивы
    entities = msp.query("POINT LINE LWPOLYLINE POLYLINE ARC CIRCLE SPLINE SOLID HATCH")

    entity: DXFGraphic
    for entity in entities:
        try:
            entity.transform(projection_matrix)
        except (AttributeError, TypeError):
            # Пропускаем объекты, которые не поддерживают трансформацию матрицей
            pass
        try:
            logger.debug("" * 30)
            logger.debug(f"DXF type: {entity.dxftype()}, на слое: {entity.dxf.layer}")

            # 2. Перевод в __geo_interface__ через GeoProxy
            proxy = GeoProxy.from_dxf_entities(entity)

            # 3. Создание объекта Shapely для валидации и WKT
            shapely_geom = shapely.geometry.shape(proxy.__geo_interface__)
            logger.debug("Shapely form: %s", shapely_geom)
            logger.debug(f"Form area: {shapely_geom.area}, length: {shapely_geom.length}")

            # Проверка на валидность (критично для полигонов из HATCH/LWPOLYLINE)
            if not shapely_geom.is_valid:
                logger.debug("Геометрия невалидна, пытаемся исправить...")
                shapely_geom = shapely.validation.make_valid(shapely_geom)
                logger.debug("Corrected shapely form: %s", shapely_geom)
                logger.debug(f"Corrected form area: {shapely_geom.area}, length: {shapely_geom.length}")

            # Получаем WKT (преимущество: читаемость и совместимость)
            wkt_data = shapely_geom.wkt
            logger.debug(f"{wkt_data=}")
            logger.debug(f"конвертирована сущность {entity.dxftype()} в WKT, размер: {len(wkt_data)} байт")

        except Exception as e:
            # Логируем сущности, которые не удалось сконвертировать (например, пустые или битые)
            print(f"Ошибка конвертации сущности {entity.dxftype()}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dxf_file", help="Путь к DWG/DXF файлу для извлечения данных")

    args = parser.parse_args()

    dxf_file = Path(args.dxf_file)
    if dxf_file.is_file():
        convert_dxf(dxf_file)
    else:
        print(f"Файл '{dxf_file}' не найден.")
        sys.exit(1)
