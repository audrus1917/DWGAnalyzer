from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from ezdxf.filemanagement import readfile


TEXT_ENTITY_TYPES = {"TEXT", "MTEXT"}


def _format_point(value: object) -> str:
    if value is None:
        return "n/a"

    if hasattr(value, "x") and hasattr(value, "y"):
        x = float(getattr(value, "x", 0.0))
        y = float(getattr(value, "y", 0.0))
        z = float(getattr(value, "z", 0.0))
        return f"({x:.2f}, {y:.2f}, {z:.2f})"

    if isinstance(value, (tuple, list)):
        numbers = [float(item) for item in value[:3]]
        while len(numbers) < 3:
            numbers.append(0.0)
        return f"({numbers[0]:.2f}, {numbers[1]:.2f}, {numbers[2]:.2f})"

    return str(value)


def _position_parts(entity: Any) -> list[str]:
    parts: list[str] = []

    for attr_name in ("insert", "location", "center", "start", "end"):
        if entity.dxf.hasattr(attr_name):
            parts.append(f"{attr_name}={_format_point(getattr(entity.dxf, attr_name))}")

    if parts:
        return parts

    if entity.dxftype() == "LWPOLYLINE":
        points = list(entity.get_points("xy"))
        if points:
            first_x, first_y = points[0][:2]
            return [
                f"first={_format_point((first_x, first_y, 0.0))}",
                f"vertices={len(points)}",
            ]

    if entity.dxftype() == "POLYLINE":
        points = list(entity.points())
        if points:
            return [f"first={_format_point(points[0])}", f"vertices={len(points)}"]

    return ["pos=n/a"]


def _entity_text(entity: Any) -> str | None:
    entity_type = entity.dxftype()
    if entity_type == "TEXT":
        return entity.dxf.text.strip()
    if entity_type == "MTEXT":
        return entity.plain_text().strip().replace("\n", " | ")
    return None


def iter_entity_descriptions(
    source_path: str | Path,
    *,
    modelspace_only: bool = False,
) -> Iterator[str]:
    doc = readfile(Path(source_path))

    spaces: list[tuple[str, Any]] = [("Model", doc.modelspace())]
    if not modelspace_only:
        for layout in doc.layouts:
            if layout.name == "Model":
                continue
            spaces.append((layout.name, layout))

    for space_name, space in spaces:
        for entity in space:
            handle = getattr(entity.dxf, "handle", "?")
            parts = [
                f"[{space_name}]",
                f"handle={handle}",
                f"type={entity.dxftype()}",
                *_position_parts(entity),
            ]
            text = _entity_text(entity)
            if text:
                parts.append(f"text={text!r}")
            yield " | ".join(parts)
