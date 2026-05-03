import sys

import logging
import argparse

from pathlib import Path

import ezdxf

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def extract_all_data(filename):
    doc = ezdxf.readfile(filename)
    msp = doc.modelspace()

    for insert in msp.query("INSERT"):
        print(f"\nБлок: {insert.dxf.name} в точке {insert.dxf.insert}")
        
        # virtual_entities() возвращает объекты уже с координатами ModelSpace
        for entity in insert.virtual_entities():
            etype = entity.dxftype()
            
            if etype == "LINE":
                print(f"  Линия: {entity.dxf.start} -> {entity.dxf.end}")
                
            elif etype == "CIRCLE" or etype == "ARC":
                print(f"  Круг/Дуга: центр {entity.dxf.center}, радиус {entity.dxf.radius}")
                
            elif etype == "LWPOLYLINE":
                # Вывод всех точек полилинии
                points = entity.get_points()
                print(f"  Полилиния: {points}")
                
            elif etype in ("TEXT", "MTEXT"):
                print(f"  Текст '{entity.dxf.text}' в точке {entity.dxf.insert}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dxf_file", help="Путь к DWG/DXF файлу для извлечения данных")
    args = parser.parse_args()

    dxf_file = Path(args.dxf_file)
    if dxf_file.is_file():
        extract_all_data(dxf_file)
    else:
        print(f"Файл '{dxf_file}' не найден.")
        sys.exit(1)
