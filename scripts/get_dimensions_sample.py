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

    for dimension in msp.query("DIMENSION"):
        print(str(dimension))
        print(f"Measurement Text: {dimension.dxf.text}")


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
