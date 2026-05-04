#!/usr/bin/env python

"""Get the extended block dscription n JSON format."""

from typing import Any, Union

import sys

import logging
import argparse
import json

from pathlib import Path

import ezdxf
from src.parsedwg.dxf_analyzer import DXFAnalyzer

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dxf_file", help="Путь к DWG/DXF файлу для извлечения данных")
    parser.add_argument("block_name", help="Наименование блока")

    args = parser.parse_args()

    dxf_file = Path(args.dxf_file)
    if dxf_file.is_file():
        doc = ezdxf.readfile(dxf_file)
        block_data = DXFAnalyzer.get_block_decsription(doc, args.block_name)
        print(json.dumps(block_data, indent=4, ensure_ascii=False))
    else:
        print(f"Файл '{dxf_file}' не найден.")
        sys.exit(1)
