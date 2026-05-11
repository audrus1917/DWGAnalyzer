#!/usr/bin/env python

import sys

import logging
import argparse

from pathlib import Path as FilePath

import ezdxf
from ezdxf import path as ezdxf_path
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
    results = {}

    for hatch in doc.modelspace().query('HATCH'):
        logger.debug(f"Обрабатываем HATCH с паттерном: {hatch.dxf.pattern_name}")
        name = hatch.dxf.pattern_name.upper()
        print(f"Паттерн: {name}")
        hatch_path = ezdxf_path.make_path(hatch)
    
        vertices = list(hatch_path.flattening(distance=0.1)) 
            
        # Формируем строку координат для WKT
        coords = ", ".join([f"{p.x} {p.y}" for p in vertices])
            
        # Замыкаем полигон, если первая и последняя точки разные
        if vertices[0] != vertices[-1]:
            coords += f", {vertices[0].x} {vertices[0].y}"
                
        print(f"POLYGON({coords})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dxf_file", help="Путь к DWG/DXF файлу для извлечения данных")

    args = parser.parse_args()
    dxf_file = FilePath(args.dxf_file)
    if not dxf_file.is_file():
        logger.error(f"Файл '{dxf_file}' не найден.")
        sys.exit(1)

    parse_dxf_hatch(dxf_file)
