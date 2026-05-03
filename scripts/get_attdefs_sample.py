"""The sample code to extract all ACAD_TABLE from a DWG/DXF file using ezdxf."""

import sys

import logging
import argparse

from pathlib import Path

import ezdxf
from ezdxf.entities.acad_table import read_acad_table_content


logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def extract_all_data(filename):
    doc = ezdxf.readfile(filename)
    msp = doc.modelspace()

    # Итерируемся по всем определениям блоков в файле
    for block in doc.blocks:
        # Игнорируем служебные блоки (слои, макеты печати и т.д.), если нужно
        # Обычно они начинаются с символа '*' (кроме анонимных блоков)
        
        attdefs = block.query("ATTDEF")
        
        if attdefs:
            for attdef in attdefs:
                name = block.name
                tag = attdef.dxf.tag
                default = attdef.dxf.text
                print(f"{name:<20} | {tag:<15} | {default:<20}")

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
