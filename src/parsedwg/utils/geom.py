"""Utilities for working with MULTILEADER in DXF files."""

from typing import Any

import logging
import re

logger = logging.getLogger(__name__)


def get_mleader_target_point(mleader):
    """Extract the point targeted by the first MULTILEADER arrow.

    Args:
        mleader: MULTILEADER DXF entity.

    Returns:
        Coordinates of the target point, or None if unavailable.
    """
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
    """Return MULTILEADER annotation text when present."""
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
    Find the closest entity of the requested types to a target point.

    .. code-block:: python

        # Example usage:
        doc = ezdxf.readfile("your_file.dxf")
        msp = doc.modelspace()

        for ml in msp.query("MULTILEADER"):
            tip = get_mleader_target_point(ml)
            target, distance = find_closest_entity(tip, msp)

            if target and distance < 1.0:  # Tolerance threshold.
                print(f"Leader '{ml.handle}' points to {target.dxftype()} ({target.handle})")

    Args:
        target_point: Point used as the search origin.
        msp: Modelspace or another object exposing query.
        search_types: DXF types to search for.

    Returns:
        Tuple of the closest entity and the distance to it, or None if no point is provided.
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
    """Find the closest entity in an already prepared DXF entity set.

    Args:
        target_point: Point used as the search origin.
        entities: Prepared DXF entity collection.
        search_types: DXF types to search for.

    Returns:
        Tuple of the closest entity and the distance to it.
    """

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


def is_point_like(value: object) -> bool:
    """Return whether a value looks like a point.

    Args:
        value: Value to inspect.

    Returns:
        True if the value looks like a point.
    """

    if hasattr(value, "x") and hasattr(value, "y"):
        return True

    if isinstance(value, (tuple, list)) and len(value) >= 2:
        try:
            float(value[0])
            float(value[1])
        except (TypeError, ValueError):
            return False
        return True

    return False


def format_point(point: Any | None) -> list[float] | None:
    """Normalize a point-like value into a consistent coordinate list.

    Args:
        point: Point object or tuple-like coordinate value.

    Returns:
        Coordinate list or None.

    Raises:
        ValueError: If point is not point-like and cannot be converted.
    """

    if point is None:
        return None

    x = getattr(point, "x", None)
    y = getattr(point, "y", None)
    z = getattr(point, "z", 0.0)
    if x is not None and y is not None:
        return [x, y, z]

    if isinstance(point, (tuple, list)) and len(point) >= 2:
        try:
            px = float(point[0])
            py = float(point[1])
            pz = float(point[2]) if len(point) >= 3 else 0.0
        except (TypeError, ValueError) as e:
            logger.warning("Failed to convert point: %s", e)
            raise

        return [px, py, pz]
    raise ValueError(f"Value is not point-like: {point}")
