#!/usr/bin/env python

from __future__ import annotations

import argparse
from pathlib import Path

import ezdxf


DEFAULT_OUTPUT = Path("_data/samples/nested_blocks_example.dxf")
ARCH_LAYER = "ARCH"
ANNO_LAYER = "ANNO"


def ensure_layers(doc: ezdxf.document.Drawing) -> None:
    if ARCH_LAYER not in doc.layers:
        doc.layers.add(ARCH_LAYER, color=7)
    if ANNO_LAYER not in doc.layers:
        doc.layers.add(ANNO_LAYER, color=2)


def add_sheet_frame(layout) -> None:
    layout.add_lwpolyline(
        [(10, 10), (410, 10), (410, 287), (10, 287), (10, 10)],
        dxfattribs={"layer": ANNO_LAYER},
    )
    layout.add_lwpolyline(
        [(15, 15), (405, 15), (405, 260), (15, 260), (15, 15)],
        dxfattribs={"layer": ANNO_LAYER},
    )


def add_title_block(layout, sheet_no: str, title: str) -> None:
    x0 = 250
    y0 = 15
    width = 155
    height = 40
    layout.add_lwpolyline(
        [(x0, y0), (x0 + width, y0), (x0 + width, y0 + height), (x0, y0 + height), (x0, y0)],
        dxfattribs={"layer": ANNO_LAYER},
    )
    for y in (y0 + 12, y0 + 24, y0 + 32):
        layout.add_line((x0, y), (x0 + width, y), dxfattribs={"layer": ANNO_LAYER})
    for x in (x0 + 28, x0 + 110):
        layout.add_line((x, y0), (x, y0 + height), dxfattribs={"layer": ANNO_LAYER})

    entries = [
        (x0 + 3, y0 + 34.5, "Лист"),
        (x0 + 31, y0 + 34.5, sheet_no),
        (x0 + 3, y0 + 22.5, "Объект"),
        (x0 + 31, y0 + 22.5, "Вложенные блоки"),
        (x0 + 3, y0 + 14.5, "Наименование"),
        (x0 + 31, y0 + 14.5, title),
        (x0 + 3, y0 + 2.5, "Масштаб"),
        (x0 + 31, y0 + 2.5, "1:50"),
        (x0 + 113, y0 + 22.5, "parsedwg sample"),
        (x0 + 113, y0 + 10.5, "2026-05-08"),
    ]
    for x, y, text in entries:
        layout.add_text(text, dxfattribs={"height": 3.2, "layer": ANNO_LAYER}).set_placement((x, y))


def add_layout(
    doc: ezdxf.document.Drawing,
    name: str,
    title: str,
    sheet_no: str,
    view_center_point: tuple[float, float],
    view_height: float,
) -> None:
    layout = doc.layouts.new(name)
    layout.page_setup(size=(420, 297), margins=(10, 10, 10, 10), units="mm", name="A3")
    layout.reset_viewports()
    add_sheet_frame(layout)
    add_title_block(layout, sheet_no=sheet_no, title=title)
    layout.add_text(title, dxfattribs={"height": 8, "layer": ANNO_LAYER}).set_placement((20, 280))
    layout.add_text(
        "Лист показывает вложенные INSERT и аннотации в блоках.",
        dxfattribs={"height": 4, "layer": ANNO_LAYER},
    ).set_placement((20, 268))
    viewport = layout.main_viewport()
    viewport.dxf.center = (210, 138)
    viewport.dxf.width = 360
    viewport.dxf.height = 220
    viewport.dxf.view_center_point = view_center_point
    viewport.dxf.view_height = view_height


def build_leaf_blocks(doc: ezdxf.document.Drawing) -> None:
    if "WINDOW_UNIT" not in doc.blocks:
        window = doc.blocks.new(name="WINDOW_UNIT")
        window.add_line((0, 0), (12, 0), dxfattribs={"layer": ARCH_LAYER})
        window.add_lwpolyline(
            [(1, -1.5), (11, -1.5), (11, 1.5), (1, 1.5), (1, -1.5)],
            dxfattribs={"layer": ARCH_LAYER},
        )
        window.add_text(
            "WINDOW_UNIT",
            dxfattribs={"height": 1.6, "layer": ANNO_LAYER},
        ).set_placement((0.5, 3.0))

    if "CHAIR_UNIT" not in doc.blocks:
        chair = doc.blocks.new(name="CHAIR_UNIT")
        chair.add_circle((0, 0), radius=2.0, dxfattribs={"layer": ARCH_LAYER})
        chair.add_line((-1.5, -2.0), (1.5, -2.0), dxfattribs={"layer": ARCH_LAYER})
        chair.add_text(
            "CHAIR_UNIT",
            dxfattribs={"height": 1.6, "layer": ANNO_LAYER},
        ).set_placement((-2.5, 3.0))


def build_parent_blocks(doc: ezdxf.document.Drawing) -> None:
    if "ROOM_MODULE" not in doc.blocks:
        room = doc.blocks.new(name="ROOM_MODULE")
        room.add_lwpolyline(
            [(0, 0), (36, 0), (36, 24), (0, 24), (0, 0)],
            dxfattribs={"layer": ARCH_LAYER},
        )
        room.add_line((18, 0), (18, 24), dxfattribs={"layer": ARCH_LAYER})
        room.add_blockref("WINDOW_UNIT", (12, 24), dxfattribs={"layer": ARCH_LAYER})
        room.add_blockref("CHAIR_UNIT", (27, 8), dxfattribs={"layer": ARCH_LAYER})
        room.add_text(
            "ROOM_MODULE",
            dxfattribs={"height": 2.5, "layer": ANNO_LAYER},
        ).set_placement((2, 26))

    if "APARTMENT_UNIT" not in doc.blocks:
        apartment = doc.blocks.new(name="APARTMENT_UNIT")
        apartment.add_lwpolyline(
            [(-2, -2), (80, -2), (80, 42), (-2, 42), (-2, -2)],
            dxfattribs={"layer": ARCH_LAYER},
        )
        apartment.add_line((40, -2), (40, 42), dxfattribs={"layer": ARCH_LAYER})
        apartment.add_blockref("ROOM_MODULE", (2, 8), dxfattribs={"layer": ARCH_LAYER})
        apartment.add_blockref("ROOM_MODULE", (42, 8), dxfattribs={"layer": ARCH_LAYER})
        apartment.add_text(
            "APARTMENT_UNIT",
            dxfattribs={"height": 3.0, "layer": ANNO_LAYER},
        ).set_placement((2, 45))


def build_example(output_path: Path) -> Path:
    doc = ezdxf.new("R2010")
    ensure_layers(doc)
    build_leaf_blocks(doc)
    build_parent_blocks(doc)

    msp = doc.modelspace()
    msp.add_blockref("APARTMENT_UNIT", (0, 0), dxfattribs={"layer": ARCH_LAYER})
    msp.add_text(
        "Пример вложенных блоков: APARTMENT_UNIT -> ROOM_MODULE -> WINDOW_UNIT/CHAIR_UNIT",
        dxfattribs={"height": 2.5, "layer": ANNO_LAYER},
    ).set_placement((0, 52))

    add_layout(
        doc,
        name="Nested_Overview",
        title="Лист 1: Общая схема вложенных блоков",
        sheet_no="01",
        view_center_point=(40, 20),
        view_height=70,
    )
    add_layout(
        doc,
        name="Room_Detail",
        title="Лист 2: Деталь ROOM_MODULE",
        sheet_no="02",
        view_center_point=(20, 18),
        view_height=36,
    )
    doc.layouts.delete("Layout1")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(output_path)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a DXF example with nested blocks and simple primitives.",
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