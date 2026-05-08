"""Утилиты для работы с MULTILEADER в DXF файлах."""

import re


def get_mleader_target_point(mleader):
    """Извлекает точку, на которую указывает первая стрелка MULTILEADER."""
    try:
        # MLeader may have multiple leaders; use the first one.
        context = mleader.context
        leader = context.leaders[0]
        line = leader.lines[0]
        # The arrow tip is the first or last vertex, depending on the type.
        return line.vertices[0] 
    except (IndexError, AttributeError):
        return None


def get_mleader_annotation_text(mleader) -> str:
    """Возвращает текст аннотации MULTILEADER, если он присутствует."""
    try:
        context = mleader.context
        mtext = getattr(context, "mtext", None)
        content = getattr(mtext, "default_content", "")
    except AttributeError:
        return ""

    text = str(content or "").strip()
    text = re.sub(r"\\P", " ", text)
    text = re.sub(r"\\[LOKlok]", "", text)
    text = re.sub(r"\\~", " ", text)

    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\{\\[^;{}]+;([^{}]*)\}", r"\1", text)

    text = re.sub(r"\\[A-Za-z][^;]*;", "", text)
    text = text.replace("{", "").replace("}", "")
    return " ".join(text.split())

def find_closest_entity(
    target_point,
    msp,
    search_types=('LINE', 'CIRCLE', 'LWPOLYLINE', 'POLYLINE', 'INSERT', 'TEXT', 'MTEXT'),
):
    """
    Ищет ближайший объект нужных типов к заданной точке.

    .. code-block:: python

        # Пример использования:
        doc = ezdxf.readfile("your_file.dxf")
        msp = doc.modelspace()

        for ml in msp.query("MULTILEADER"):
            tip = get_mleader_target_point(ml)
            target, distance = find_closest_entity(tip, msp)

            if target and distance < 1.0:  # Порог допуска.
                print(f"Leader '{ml.handle}' points to {target.dxftype()} ({target.handle})")
    """

    if not target_point:
        return None
    
    min_dist = float('inf')
    closest_entity = None
    
    for entity in msp.query('|'.join(search_types)):
        # Compute the distance from the point to the entity in a simplified way.
        # For exact curve distance, use .bbox() or .dist_to_entity() style methods.
        try:
            bbox = entity.bounding_box()
            dist = bbox.center.distance(target_point) # Rough estimate via center point.
            
            if dist < min_dist:
                min_dist = dist
                closest_entity = entity
        except Exception:
            continue
            
    return closest_entity, min_dist


def find_closest_entity_in_entities(
    target_point,
    entities,
    search_types=('LINE', 'CIRCLE', 'LWPOLYLINE', 'POLYLINE', 'INSERT', 'TEXT', 'MTEXT'),
):
    """Ищет ближайшую сущность в уже подготовленном наборе DXF-сущностей."""

    if not target_point:
        return None, float('inf')

    normalized_types = {str(value).upper() for value in search_types}
    min_dist = float('inf')
    closest_entity = None

    for entity in entities:
        try:
            if str(entity.dxftype()).upper() not in normalized_types:
                continue
            bbox = entity.bounding_box()
            dist = bbox.center.distance(target_point)
            if dist < min_dist:
                min_dist = dist
                closest_entity = entity
        except Exception:
            continue

    return closest_entity, min_dist
