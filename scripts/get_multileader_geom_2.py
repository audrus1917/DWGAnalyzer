import ezdxf
from ezdxf.render.mleader import MLeaderContext

def process_mleaders(dxf_path):
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    results = []

    for ml in msp.query("MULTILEADER"):
        # 1. Извлекаем текст
        # Контент лежит в mleader.context.mtext
        text_content = ""
        if ml.context.mtext:
            text_content = ml.context.mtext.default_text
        
        # 2. Точка вставки текста (для аннотации в PostGIS)
        # Это координата, куда ГИС привяжет подпись
        ins_pt = ml.context.base_point  # (x, y, z)

        # 3. Собираем линии выносок в единый массив для MultiLineString
        line_segments = []
        
        # Используем virtual_entities, чтобы получить "отрисованные" линии
        # Это надежнее, чем вручную перебирать вершины в сложных стилях
        for entity in ml.virtual_entities():
            if entity.dxftype() == 'LINE':
                start = entity.dxf.start
                end = entity.dxf.end
                # Формируем сегмент в формате WKT: (x1 y1, x2 y2)
                line_segments.append(f"({start.x} {start.y}, {end.x} {end.y})")

        # Формируем WKT для MultiLineString
        multiline_wkt = f"MULTILINESTRING({', '.join(line_segments)})"
        point_wkt = f"POINT({ins_pt.x} {ins_pt.y})"

        results.append({
            'handle': ml.dxf.handle,
            'geom': multiline_wkt,
            'text_point': point_wkt,
            'text': text_content,
            'angle': ml.context.mtext.rotation if ml.context.mtext else 0
        })
    
    return results

# Пример формирования SQL (используя psycopg2 или аналоги)
# query = "INSERT INTO dwg_mleaders (geom, text_point, label_text, text_angle) 
#          VALUES (ST_GeomFromText(%s, 4326), ST_GeomFromText(%s, 4326), %s, %s)"
