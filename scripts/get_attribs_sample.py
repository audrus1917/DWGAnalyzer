"""The sample code to extract all attributes from a DWG/DXF file using ezdxf.
This includes:
- Block attributes (from INSERT and POLYLINE)
- Extended data (XDATA)
- Extension dictionaries (XRECORDs attached to entities)
- Global dictionaries (XRECORDs in the root dictionary).
"""

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

    # 1. Атрибуты (из INSERT и POLYLINE)
    for entity in msp.query("INSERT POLYLINE"):
        # Для INSERT используем .attribs
        if entity.dxftype() == "INSERT" and entity.attribs:
            for attr in entity.attribs:
                print(f"Атрибут Блока: [{attr.dxf.tag}] = {attr.dxf.text}")

        # Для старых POLYLINE перебираем вложенные сущности
        elif entity.dxftype() == "POLYLINE":
            for sub in entity.sub_entities():
                if sub.dxftype() == "ATTRIB":
                    print(f"Атрибут Полилинии: {sub.dxf.text}")

    # 2. XDATA (Расширенные данные практически у любого объекта)
    for entity in msp:
        if entity.xdata:
            for appid, tags in entity.xdata.data.items():
                print(f"XDATA (AppID: {appid}): {tags}")

    # 3. Словари расширения (Extension Dictionaries) у объектов
    for entity in msp:
        if entity.has_extension_dict:
            xdict = entity.get_extension_dict()
            for name, obj in xdict.items():
                if obj.dxftype() == "XRECORD":
                    print(f"XRECORD в объекте: {name} = {obj.tags}")

    # 4. Глобальные словари (Root Dictionary)
    print("\nГлобальные данные чертежа:")
    for name, obj in doc.rootdict.items():
        if obj.dxftype() == "XRECORD":
            print(f"Глобальный XRECORD '{name}': {obj.tags}")
        elif obj.dxftype() == "DICTIONARY":
            print(f"Вложенный словарь '{name}' найден")


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
