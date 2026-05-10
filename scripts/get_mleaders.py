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
    results = []

    for ml in msp.query("MULTILEADER"):
        # 1. Извлекаем текст
        # Контент лежит в mleader.context.mtext
        # text_content = ""
        # if ml.context.mtext:
        #     text_content = ml.context.mtext.default_text
        
        # 2. Точка вставки текста (для аннотации в PostGIS)
        # Это координата, куда ГИС привяжет подпись
        ins_pt = ml.context.base_point  # (x, y, z)

        # 3. Собираем линии выносок в единый массив для MultiLineString
        line_segments = []
        
        # Используем virtual_entities, чтобы получить "отрисованные" линии
        # Это надежнее, чем вручную перебирать вершины в сложных стилях
        text_content = ml.get_mtext_content() if hasattr(ml, "get_mtext_content") else ""
        for entity in ml.virtual_entities():
            dxf_type = entity.dxftype()
            if entity.dxftype() == 'LINE':
                start = entity.dxf.start
                end = entity.dxf.end
                # Формируем сегмент в формате WKT: (x1 y1, x2 y2)
                line_segments.append(f"({start.x} {start.y}, {end.x} {end.y})")
            elif entity.dxftype() == 'POLYLINE':
                points = [vertex.dxf.location.xyz for vertex in entity.vertices]
                for i in range(len(points) - 1):
                    start = points[i]
                    end = points[i + 1]
                    line_segments.append(f"({start[0]} {start[1]}, {end[0]} {end[1]})")    
            elif entity.dxftype() == 'LWPOLYLINE':
                points = entity.get_points("xy")
                for i in range(len(points) - 1):
                    start = points[i]
                    end = points[i + 1]
                    line_segments.append(f"({start[0]} {start[1]}, {end[0]} {end[1]})")
    

        # Формируем WKT для MultiLineString
        multiline_wkt = f"MULTILINESTRING({', '.join(line_segments)})"
        point_wkt = f"POINT({ins_pt.x} {ins_pt.y})"

        results.append({
            'handle': ml.dxf.handle,
            'geom': multiline_wkt,
            'text_point': point_wkt,
            'text': text_content,
            # 'angle': ml.context.mtext.rotation if ml.context.mtext else 0
        })
    
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dxf_file", help="Путь к DWG/DXF файлу для извлечения данных")

    args = parser.parse_args()
    dxf_file = FilePath(args.dxf_file)
    if not dxf_file.is_file():
        logger.error(f"Файл '{dxf_file}' не найден.")
        sys.exit(1)

    result = process_mleaders(dxf_file)
    print(json.dumps(result, indent=2, ensure_ascii=False))

# Пример формирования SQL (используя psycopg2 или аналоги)
# query = "INSERT INTO dwg_mleaders (geom, text_point, label_text, text_angle) 
#          VALUES (ST_GeomFromText(%s, 4326), ST_GeomFromText(%s, 4326), %s, %s)"
