#!/usr/bin/env python

from __future__ import annotations

import argparse
from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment


DEFAULT_OUTPUT = Path("_data/samples/house_two_floors_example.dxf")
ARCH_LAYER = "ARCH"
ANNO_LAYER = "ANNO"
FLOOR_WIDTH = 70
FLOOR_HEIGHT = 45


def add_common_furniture_attdefs(block) -> None:
    block.add_attdef("ITEM", insert=(0, -3), dxfattribs={"height": 1.3, "layer": ANNO_LAYER})
    block.add_attdef("ROOM", insert=(0, -5), dxfattribs={"height": 1.3, "layer": ANNO_LAYER})
    block.add_attdef("FLOOR", insert=(0, -7), dxfattribs={"height": 1.3, "layer": ANNO_LAYER})


def add_common_marker_attdefs(block, tag_names: list[str]) -> None:
    for index, tag_name in enumerate(tag_names, start=1):
        block.add_attdef(
            tag_name,
            insert=(0, -2.2 * index),
            dxfattribs={"height": 1.2, "layer": ANNO_LAYER},
        )


def ensure_layers(doc: ezdxf.document.Drawing) -> None:
    if ARCH_LAYER not in doc.layers:
        doc.layers.add(ARCH_LAYER, color=7)
    if ANNO_LAYER not in doc.layers:
        doc.layers.add(ANNO_LAYER, color=2)


def ensure_furniture_blocks(doc: ezdxf.document.Drawing) -> None:
    if "BED" not in doc.blocks:
        bed = doc.blocks.new(name="BED")
        bed.add_lwpolyline(
            [(0, 0), (18, 0), (18, 12), (0, 12), (0, 0)],
            dxfattribs={"layer": ARCH_LAYER},
        )
        bed.add_line((1.5, 10), (6.5, 10), dxfattribs={"layer": ARCH_LAYER})
        bed.add_line((11.5, 10), (16.5, 10), dxfattribs={"layer": ARCH_LAYER})
        add_common_furniture_attdefs(bed)

    if "SOFA" not in doc.blocks:
        sofa = doc.blocks.new(name="SOFA")
        sofa.add_lwpolyline(
            [(0, 0), (16, 0), (16, 6), (0, 6), (0, 0)],
            dxfattribs={"layer": ARCH_LAYER},
        )
        sofa.add_line((2, 1), (14, 1), dxfattribs={"layer": ARCH_LAYER})
        sofa.add_line((2, 5), (14, 5), dxfattribs={"layer": ARCH_LAYER})
        add_common_furniture_attdefs(sofa)

    if "DINING" not in doc.blocks:
        dining = doc.blocks.new(name="DINING")
        dining.add_circle((0, 0), radius=4, dxfattribs={"layer": ARCH_LAYER})
        for point in ((0, 7), (0, -7), (7, 0), (-7, 0)):
            dining.add_circle(point, radius=1.3, dxfattribs={"layer": ARCH_LAYER})
        add_common_furniture_attdefs(dining)

    if "DESK" not in doc.blocks:
        desk = doc.blocks.new(name="DESK")
        desk.add_lwpolyline(
            [(0, 0), (10, 0), (10, 5), (0, 5), (0, 0)],
            dxfattribs={"layer": ARCH_LAYER},
        )
        desk.add_circle((5, -2), radius=1.2, dxfattribs={"layer": ARCH_LAYER})
        add_common_furniture_attdefs(desk)

    if "ROOM_TAG" not in doc.blocks:
        room_tag = doc.blocks.new(name="ROOM_TAG")
        room_tag.add_circle((0, 0), radius=2.4, dxfattribs={"layer": ANNO_LAYER})
        room_tag.add_line((-1.7, 0), (1.7, 0), dxfattribs={"layer": ANNO_LAYER})
        room_tag.add_line((0, -1.7), (0, 1.7), dxfattribs={"layer": ANNO_LAYER})
        add_common_marker_attdefs(room_tag, ["ROOM_NAME", "AREA", "FLOOR"])

    if "DOOR_TAG" not in doc.blocks:
        door_tag = doc.blocks.new(name="DOOR_TAG")
        door_tag.add_lwpolyline(
            [(-2, -1), (2, -1), (2, 1), (-2, 1), (-2, -1)],
            dxfattribs={"layer": ANNO_LAYER},
        )
        door_tag.add_text(
            "D",
            dxfattribs={"height": 1.6, "layer": ANNO_LAYER},
        ).set_placement((-0.6, -0.6))
        add_common_marker_attdefs(door_tag, ["DOOR_ID", "OPENS_TO", "FLOOR"])


def add_room_label(msp, text: str, x: float, y: float) -> None:
    msp.add_text(
        text,
        dxfattribs={"height": 2.5, "layer": ANNO_LAYER},
    ).set_placement((x, y))


def add_dimension_note(msp, text: str, start: tuple[float, float], end: tuple[float, float]) -> None:
    msp.add_line(start, end, dxfattribs={"layer": ANNO_LAYER, "linetype": "DASHED"})
    msp.add_text(
        text,
        dxfattribs={"height": 2.0, "layer": ANNO_LAYER},
    ).set_placement(
        ((start[0] + end[0]) / 2, end[1] + 1.5),
        align=TextEntityAlignment.MIDDLE_CENTER,
    )


def add_wall_hatch(msp, points: list[tuple[float, float]]) -> None:
    hatch = msp.add_hatch(color=8, dxfattribs={"layer": ARCH_LAYER})
    hatch.set_pattern_fill("ANSI31", scale=0.5)
    hatch.paths.add_polyline_path(points, is_closed=True)


def add_furniture_ref(
    msp,
    block_name: str,
    insert: tuple[float, float],
    room: str,
    floor_number: int,
):
    reference = msp.add_blockref(block_name, insert, dxfattribs={"layer": ARCH_LAYER})
    reference.add_auto_attribs(
        {
            "ITEM": block_name,
            "ROOM": room,
            "FLOOR": str(floor_number),
        }
    )
    return reference


def add_marker_ref(msp, block_name: str, insert: tuple[float, float], values: dict[str, str]):
    reference = msp.add_blockref(block_name, insert, dxfattribs={"layer": ANNO_LAYER})
    reference.add_auto_attribs(values)
    return reference


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
        (x0 + 31, y0 + 22.5, "Учебный план дома"),
        (x0 + 3, y0 + 14.5, "Наименование"),
        (x0 + 31, y0 + 14.5, title),
        (x0 + 3, y0 + 2.5, "Масштаб"),
        (x0 + 31, y0 + 2.5, "1:100"),
        (x0 + 113, y0 + 22.5, "parsedwg sample"),
        (x0 + 113, y0 + 10.5, "2026-05-07"),
    ]
    for x, y, text in entries:
        layout.add_text(text, dxfattribs={"height": 3.2, "layer": ANNO_LAYER}).set_placement((x, y))


def add_floor_layout(
    doc: ezdxf.document.Drawing,
    name: str,
    title: str,
    sheet_no: str,
    view_center_point: tuple[float, float],
) -> None:
    layout = doc.layouts.new(name)
    layout.page_setup(size=(420, 297), margins=(10, 10, 10, 10), units="mm", name="A3")
    layout.reset_viewports()
    add_sheet_frame(layout)
    add_title_block(layout, sheet_no=sheet_no, title=title)
    layout.add_text(
        title,
        dxfattribs={"height": 8, "layer": ANNO_LAYER},
    ).set_placement((20, 280))
    layout.add_text(
        "Лист с viewport, штампом и атрибутами мебели, дверей и помещений.",
        dxfattribs={"height": 4, "layer": ANNO_LAYER},
    ).set_placement((20, 268))
    viewport = layout.main_viewport()
    viewport.dxf.center = (210, 138)
    viewport.dxf.width = 360
    viewport.dxf.height = 220
    viewport.dxf.view_center_point = view_center_point
    viewport.dxf.view_height = 72


def add_floor_outline(msp, origin_x: float, origin_y: float, title: str) -> None:
    width = FLOOR_WIDTH
    height = FLOOR_HEIGHT
    outer = [
        (origin_x, origin_y),
        (origin_x + width, origin_y),
        (origin_x + width, origin_y + height),
        (origin_x, origin_y + height),
        (origin_x, origin_y),
    ]
    msp.add_lwpolyline(outer, dxfattribs={"layer": ARCH_LAYER})

    walls = [
        ((origin_x + 24, origin_y), (origin_x + 24, origin_y + 28)),
        ((origin_x, origin_y + 20), (origin_x + 24, origin_y + 20)),
        ((origin_x + 42, origin_y + 18), (origin_x + width, origin_y + 18)),
    ]
    for start, end in walls:
        msp.add_line(start, end, dxfattribs={"layer": ARCH_LAYER})

    hatched_wall = [
        (origin_x + 23, origin_y + 8),
        (origin_x + 25, origin_y + 8),
        (origin_x + 25, origin_y + 19),
        (origin_x + 23, origin_y + 19),
    ]
    add_wall_hatch(msp, hatched_wall)

    msp.add_arc(
        center=(origin_x + 24, origin_y + 6),
        radius=5,
        start_angle=270,
        end_angle=360,
        dxfattribs={"layer": ARCH_LAYER},
    )
    msp.add_line(
        (origin_x + 24, origin_y + 6),
        (origin_x + 29, origin_y + 6),
        dxfattribs={"layer": ARCH_LAYER},
    )

    add_room_label(msp, title, origin_x + 35, origin_y + height + 5)
    add_room_label(msp, "Гостиная", origin_x + 10, origin_y + 10)
    add_room_label(msp, "Кухня", origin_x + 10, origin_y + 31)
    add_room_label(msp, "Спальня", origin_x + 50, origin_y + 10)
    add_room_label(msp, "С/У", origin_x + 52, origin_y + 31)
    add_dimension_note(
        msp,
        "7000",
        (origin_x, origin_y - 4),
        (origin_x + width, origin_y - 4),
    )


def add_room_tags(msp, origin_x: float, origin_y: float, floor_number: int) -> None:
    add_marker_ref(
        msp,
        "ROOM_TAG",
        (origin_x + 18, origin_y + 9),
        {"ROOM_NAME": "Гостиная", "AREA": "18 м2", "FLOOR": str(floor_number)},
    )
    add_marker_ref(
        msp,
        "ROOM_TAG",
        (origin_x + 16, origin_y + 30),
        {"ROOM_NAME": "Кухня", "AREA": "13 м2", "FLOOR": str(floor_number)},
    )
    add_marker_ref(
        msp,
        "ROOM_TAG",
        (origin_x + 57, origin_y + 10),
        {"ROOM_NAME": "Спальня", "AREA": "16 м2", "FLOOR": str(floor_number)},
    )


def add_door_tags(msp, origin_x: float, origin_y: float, floor_number: int) -> None:
    add_marker_ref(
        msp,
        "DOOR_TAG",
        (origin_x + 28, origin_y + 6),
        {"DOOR_ID": f"D-{floor_number}01", "OPENS_TO": "Гостиная", "FLOOR": str(floor_number)},
    )
    add_marker_ref(
        msp,
        "DOOR_TAG",
        (origin_x + 24, origin_y + 20),
        {"DOOR_ID": f"D-{floor_number}02", "OPENS_TO": "Кухня", "FLOOR": str(floor_number)},
    )


def add_furniture(msp, origin_x: float, origin_y: float, floor_number: int) -> None:
    add_furniture_ref(msp, "SOFA", (origin_x + 4, origin_y + 5), "Гостиная", floor_number)
    add_furniture_ref(
        msp,
        "DINING",
        (origin_x + 10, origin_y + 30),
        "Кухня",
        floor_number,
    )
    add_furniture_ref(msp, "BED", (origin_x + 44, origin_y + 4), "Спальня", floor_number)

    if floor_number == 1:
        add_furniture_ref(msp, "DESK", (origin_x + 48, origin_y + 27), "Кабинет", floor_number)
        note = "1 этаж: вход, общая зона и кабинет"
    else:
        add_furniture_ref(msp, "DESK", (origin_x + 6, origin_y + 24), "Кабинет", floor_number)
        note = "2 этаж: спальня, рабочее место и санузел"

    add_room_label(msp, note, origin_x + 35, origin_y - 10)
    add_room_tags(msp, origin_x, origin_y, floor_number)
    add_door_tags(msp, origin_x, origin_y, floor_number)


def add_schedule_table(msp, insert_x: float, insert_y: float) -> None:
    column_widths = [16, 20, 12]
    row_height = 5
    rows = [
        ["Этаж", "Помещение", "Площадь"],
        ["1", "Гостиная + кухня", "31 м2"],
        ["2", "Спальня + кабинет", "28 м2"],
    ]
    total_width = sum(column_widths)
    total_height = row_height * len(rows)

    for row_index in range(len(rows) + 1):
        y = insert_y - row_index * row_height
        msp.add_line(
            (insert_x, y),
            (insert_x + total_width, y),
            dxfattribs={"layer": ANNO_LAYER},
        )

    current_x = insert_x
    for width in [0, *column_widths]:
        msp.add_line(
            (current_x, insert_y),
            (current_x, insert_y - total_height),
            dxfattribs={"layer": ANNO_LAYER},
        )
        current_x += width

    for row_index, row in enumerate(rows):
        y = insert_y - row_index * row_height - 3.5
        x = insert_x + 1.5
        for column_index, value in enumerate(row):
            msp.add_text(
                value,
                dxfattribs={"height": 2.2, "layer": ANNO_LAYER},
            ).set_placement((x, y))
            x += column_widths[column_index]

    add_room_label(msp, "Экспликация помещений", insert_x + total_width / 2, insert_y + 4)


def build_example(output_path: Path) -> Path:
    doc = ezdxf.new("R2010")
    ensure_layers(doc)
    ensure_furniture_blocks(doc)

    msp = doc.modelspace()
    add_floor_outline(msp, 0, 0, "План 1 этажа")
    add_furniture(msp, 0, 0, floor_number=1)
    add_floor_outline(msp, 90, 0, "План 2 этажа")
    add_furniture(msp, 90, 0, floor_number=2)
    add_schedule_table(msp, 0, 70)

    add_room_label(msp, "Штриховка стены: ANSI31", 35, 58)
    add_room_label(msp, "Слои: ARCH и ANNO", 135, 58)
    add_room_label(msp, "У блоков есть атрибуты: мебель, двери и маркеры помещений", 65, 65)

    add_floor_layout(
        doc,
        "Этаж_1",
        "Лист 1: План первого этажа",
        "01",
        (FLOOR_WIDTH / 2, FLOOR_HEIGHT / 2),
    )
    add_floor_layout(
        doc,
        "Этаж_2",
        "Лист 2: План второго этажа",
        "02",
        (90 + FLOOR_WIDTH / 2, FLOOR_HEIGHT / 2),
    )
    doc.layouts.delete("Layout1")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(output_path)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a simple two-floor house DXF example with blocks and annotations.",
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