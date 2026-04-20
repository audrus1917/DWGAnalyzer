#!/usr/bin/env python3
"""Find viewport sizes in a DWG/DXF drawing.

Usage:
  PYTHONPATH=src ./.venv/bin/python scripts/find_viewports.py /path/to/file.dxf
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ezdxf.addons.odafc import readfile as read_odafc
from ezdxf.filemanagement import readfile


def _format_point(value: object | None) -> list[float] | None:
    if value is None:
        return None

    x = getattr(value, "x", None)
    y = getattr(value, "y", None)
    z = getattr(value, "z", None)
    if x is not None and y is not None:
        if z is None:
            return [float(x), float(y)]
        return [float(x), float(y), float(z)]

    if isinstance(value, (tuple, list)) and len(value) >= 2:
        try:
            x_value = float(value[0])
            y_value = float(value[1])
            if len(value) >= 3:
                return [x_value, y_value, float(value[2])]
            return [x_value, y_value]
        except (TypeError, ValueError):
            return None

    return None


def _read_document(path: Path):
    suffix = path.suffix.lower()
    if suffix == ".dwg":
        return read_odafc(path, "ACAD2018")
    if suffix == ".dxf":
        return readfile(path)
    raise ValueError("Supported file types: .dwg, .dxf")


def collect_viewports(path: Path) -> list[dict[str, object]]:
    doc = _read_document(path)
    
    print("EXTMAX ", doc.header['$EXTMAX'])
    print("EXTMIN ", doc.header['$EXTMIN'])
    print("LIMMAX ", doc.header['$LIMMAX'])
    print("LIMMIN ", doc.header['$LIMMIN'])    
    
    rows: list[dict[str, object]] = []

    for layout in doc.layouts:
        for entity in layout.query("VIEWPORT"):
            rows.append(
                {
                    "drawing": str(path),
                    "layout": layout.name,
                    "handle": getattr(entity.dxf, "handle", ""),
                    "viewport_center": _format_point(getattr(entity.dxf, "center", None)),
                    "viewport_width": float(getattr(entity.dxf, "width", 0.0)),
                    "viewport_height": float(getattr(entity.dxf, "height", 0.0)),
                    "view_center_point": _format_point(
                        getattr(entity.dxf, "view_center_point", None)
                    ),
                    "view_height": float(getattr(entity.dxf, "view_height", 0.0)),
                    "status": int(getattr(entity.dxf, "status", 0)),
                }
            )

    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read DWG/DXF and print viewport sizes as JSON."
    )
    parser.add_argument("path", help="Path to DWG or DXF file.")
    args = parser.parse_args()

    drawing_path = Path(args.path)
    if not drawing_path.is_file():
        raise FileNotFoundError(f"File not found: {drawing_path}")

    rows = collect_viewports(drawing_path)
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
