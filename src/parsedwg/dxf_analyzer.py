"""Класс анализа и извлечения данных из формата `DXF`."""

from typing import Any, Optional

import json
import re

from ezdxf.document import Drawing


class DXFAnalyzer:
    """Анализирует и извлекает данные из формата `DXF`."""

    def __init__(self, drawing: Drawing):
        self.drawing = drawing

    @staticmethod
    def is_point_like(value: object) -> bool:
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

    @staticmethod
    def format_point(point: object | None) -> Optional[list[float]]:
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
            except (TypeError, ValueError):
                return str(point)
            return [px, py, pz]

        return point


    @staticmethod
    def get_text(entity) -> str:
        entity_type = entity.dxftype()
        if entity_type == "TEXT" and entity.dxf.hasattr("text"):
            return str(entity.dxf.text).strip()

        if entity_type == "MTEXT":
            plain_text = getattr(entity, "plain_text", None)
            if callable(plain_text):
                return str(plain_text()).strip()

        return ""

    @classmethod
    def get_entity_data(cls, entity, block: Optional[object] = None) -> dict[str, Any]:
        """Возвращает данные DXF-сущности."""

        # Получаем тип сущности и базовые атрибуты
        dxftype = entity.dxftype()

        # Общая обработка
        entity_data = {
            "type": dxftype,
            "block": getattr(block, "name", None) if block is not None else None,
            "layer": entity.dxf.layer if hasattr(entity.dxf, "layer") else None,
        }
        if text_value := cls.get_text(entity):
            entity_data["text"] = re.sub(r"\s+", " ", text_value).strip()

        for attr_name, value in entity.dxf.all_existing_dxf_attribs().items():
            if cls.is_point_like(value):
                entity_data[attr_name] = cls.format_point(value)
            else:
                entity_data[attr_name] = value

        match dxftype:
            case "INSERT":
                entity_data["block"] = entity.dxf.name
            case "LWPOLYLINE":
                points = entity.get_points("xy")
                entity_data["points"] = [cls.format_point(point) for point in points]
            case "POLYLINE":
                points = [vertex.dxf.location.xyz for vertex in entity.vertices]
                entity_data["points"] = [cls.format_point(point) for point in points]
            case "LINE":
                entity_data["start"] = cls.format_point(entity.dxf.start)
                entity_data["end"] = cls.format_point(entity.dxf.end)
                entity_data["geom"] = "SRID=4326;LINESTRING({} {}, {} {})".format(
                    entity.dxf.start.x, entity.dxf.start.y, entity.dxf.end.x, entity.dxf.end.y
                )
            case "CIRCLE":
                entity_data["center"] = cls.format_point(entity.dxf.center)
                entity_data["radius"] = entity.dxf.radius
            case "ARC":
                entity_data["center"] = cls.format_point(entity.dxf.center)
                entity_data["radius"] = entity.dxf.radius
                entity_data["start_angle"] = entity.dxf.start_angle
                entity_data["end_angle"] = entity.dxf.end_angle

        rendered: list[str] = []
        for key, value in entity_data.items():
            if key in {"block", "text"}:
                rendered.append(f"{key}={value!r}")
            else:
                rendered.append(f"{key}={value}")
        return entity_data
