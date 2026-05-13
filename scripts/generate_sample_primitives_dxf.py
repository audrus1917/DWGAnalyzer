#!/usr/bin/env python

from __future__ import annotations

import argparse
from pathlib import Path

import ezdxf


DEFAULT_OUTPUT = Path("_samples/primitives_polyline_example.dxf")
ARCH_LAYER = "ARCH"
ANNO_LAYER = "ANNO"


def ensure_layers(doc: ezdxf.document.Drawing) -> None:
    if ARCH_LAYER not in doc.layers:
        doc.layers.add(ARCH_LAYER, color=7)
    if ANNO_LAYER not in doc.layers:
        doc.layers.add(ANNO_LAYER, color=2)


def add_label(msp, text: str, x: float, y: float) -> None:
    msp.add_text(
        text,
        dxfattribs={"height": 2.5, "layer": ANNO_LAYER},
    ).set_placement((x, y))


def build_example(output_path: Path) -> Path:
    doc = ezdxf.new("R2010")
    ensure_layers(doc)

    msp = doc.modelspace()

    add_label(msp, "LWPOLYLINE open", 0, 32)
    msp.add_lwpolyline(
        [(0, 20), (10, 28), (22, 22), (34, 28)],
        dxfattribs={"layer": ARCH_LAYER},
    )

    add_label(msp, "LWPOLYLINE closed", 50, 32)
    msp.add_lwpolyline(
        [(50, 20), (68, 20), (72, 30), (56, 36)],
        close=True,
        dxfattribs={"layer": ARCH_LAYER},
    )

    add_label(msp, "LWPOLYLINE closed, 2 pts, bulge + / -", 100, 32)
    msp.add_lwpolyline(
        [
            (100, 24, 0, 0, 1.0),
            (122, 24, 0, 0, -0.45),
        ],
        format="xyseb",
        close=True,
        dxfattribs={"layer": ARCH_LAYER},
    )

    add_label(msp, "POLYLINE open", 0, 72)
    msp.add_polyline2d(
        [(0, 56), (8, 64), (20, 58), (32, 66)],
        dxfattribs={"layer": ARCH_LAYER},
    )

    add_label(msp, "POLYLINE closed", 50, 72)
    polyline_closed = msp.add_polyline2d(
        [(50, 56), (66, 56), (74, 66), (58, 70)],
        dxfattribs={"layer": ARCH_LAYER},
    )
    polyline_closed.close(True)

    add_label(msp, "LINE", 100, 72)
    msp.add_line((100, 58), (128, 68), dxfattribs={"layer": ARCH_LAYER})

    add_label(msp, "SOLID", 150, 72)
    msp.add_solid(
        [(150, 56), (172, 58), (168, 72), (154, 68)],
        dxfattribs={"layer": ARCH_LAYER},
    )

    add_label(msp, "Учебный пример примитивов DXF", 0, 100)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(output_path)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a DXF example with LINE, SOLID, LWPOLYLINE, and POLYLINE entities.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output DXF path. Default: {DEFAULT_OUTPUT}",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = build_example(args.output)
    print(output_path)


if __name__ == "__main__":
    main()