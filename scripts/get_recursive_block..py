#!/usr/bin/env python

"""Get the recursive layers from DXF block."""

import logging
import argparse
import json

from pathlib import Path

import ezdxf



logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def analyze_block_full(block_name, doc, data=None, processed=None):
    if data is None:
        data = {
            "primitives_layers": set(), 
            "nested_blocks": set(),
            "text_content": set(),
            "attdefs": []  # Список определений атрибутов
        }
    if processed is None:
        processed = set()

    if block_name in processed:
        return data
    processed.add(block_name)

    block_def = doc.blocks.get(block_name)
    if not block_def:
        return data

    for entity in block_def:
        # 1. Слои
        data["primitives_layers"].add(entity.dxf.layer)
        
        # 2. Текст (TEXT и MTEXT)
        if entity.dxftype() in ('TEXT', 'MTEXT'):
            val = entity.dxf.text.strip()
            if val: data["text_content"].add(val)
        
        # 3. ATTDEFS (Определения атрибутов)
        if entity.dxftype() == 'ATTDEF':
            data["attdefs"].append({
                "tag": entity.dxf.tag,
                "prompt": getattr(entity.dxf, 'prompt', ''), # Подсказка для пользователя
                "default": entity.dxf.text # Значение по умолчанию
            })
        
        # 4. Рекурсия для вложенных вставок
        if entity.dxftype() == 'INSERT':
            nested_name = entity.dxf.name
            data["nested_blocks"].add(nested_name)
            analyze_block_full(nested_name, doc, data, processed)
            
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dxf_file", help="Путь к DWG/DXF файлу для извлечения данных")

    args = parser.parse_args()

    dxf_file = Path(args.dxf_file)
    if not dxf_file.is_file():
        logger.error("File not found")

    # Основной процесс
    doc = ezdxf.readfile(dxf_file)
    msp = doc.modelspace()

    results = []

    for insert in msp.query('INSERT'):
        internal = analyze_block_full(insert.dxf.name, doc)
        
        # Собираем заполненные значения атрибутов именно этой вставки (ATTRIB)
        current_attributes = {attr.dxf.tag: attr.dxf.text for attr in insert.attribs}
        
        block_info = {
            "block_name": insert.dxf.name,
            "block_layer": insert.dxf.layer,
        }
        
        if primitives_layers := list(internal["primitives_layers"]):
            block_info["primitives_layers"] = primitives_layers
        if nested_blocks := list(internal["nested_blocks"]):
            block_info["nested_blocks"] = nested_blocks
        if text_content := list(internal["text_content"]):
            block_info["text_content"] = text_content
        if attdefs := internal["attdefs"]:
            block_info["attdefs"] = attdefs
        if current_attributes:
            block_info["attribs"] = current_attributes
        results.append(block_info)

    print(json.dumps(results, indent=4, ensure_ascii=False))