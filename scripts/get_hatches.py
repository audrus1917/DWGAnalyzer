#!/usr/bin/env python

import sys

import logging
import argparse

from pathlib import Path as FilePath

import ezdxf
from ezdxf import path
from ezdxf.math import area as math_area

from src.parsedwg.dxf_analyzer import DXFAnalyzer

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# Словарь расшифровки материалов
ANSI_MAP = {
    'ANSI31': 'Чугун / Кирпич',
    'ANSI32': 'Сталь',
    'ANSI33': 'Медь / Латунь',
    'ANSI34': 'Пластик / Резина',
    'ANSI35': 'Огнеупорный кирпич',
    'ANSI36': 'Мрамор / Стекло',
    'ANSI37': 'Свинец / Изоляция',
    'ANSI38': 'Алюминий'
}

def parse_dxf_hatch(filename):
    try:
        doc = ezdxf.readfile(filename)
    except Exception as e:
        print(f"Ошибка при открытии файла: {e}")
        return

    logger.debug("Единицы измерения: {}".format(doc.header['$INSUNITS']))
    msp = doc.modelspace()
    results = {}

    for hatch in msp.query('HATCH'):
        logger.debug(f"Обрабатываем HATCH с паттерном: {hatch.dxf.pattern_name}")
        name = hatch.dxf.pattern_name.upper()
        try:
            # Получаем геометрию и считаем площадь (вычитает дырки автоматически)
            hatch_path = path.make_path(hatch)
            vertices = list(hatch_path.flattening(distance=0.01))
            print(vertices)
            for x in vertices:
                print(DXFAnalyzer.format_point(x))
                
            path_area = math_area(vertices)
            if name not in results:
                results[name] = {'area': 0, 'count': 0}
            
            results[name]['area'] += path_area
            results[name]['count'] += 1
        except Exception as e:
            logger.error(f"Ошибка при обработке HATCH: {e}")
            continue

    # Вывод в консоль
    print(f"\n{'Код':<10} | {'Материал':<20} | {'Кол-во':<8} | {'Общая площадь':<15}")
    print("-" * 60)
    
    for code, data in results.items():
        material_name = ANSI_MAP.get(code, "Другой материал")
        print(f"{code:<10} | {material_name:<20} | {data['count']:<8} | {data['area']:<15.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dxf_file", help="Путь к DWG/DXF файлу для извлечения данных")

    args = parser.parse_args()
    dxf_file = FilePath(args.dxf_file)
    if not dxf_file.is_file():
        logger.error(f"Файл '{dxf_file}' не найден.")
        sys.exit(1)

    parse_dxf_hatch(dxf_file)
