from io import BytesIO

from openpyxl import load_workbook

from parsedwg.models import ParsedItem
from parsedwg.parsers import parse_item_line
from parsedwg.reporting import build_workbook_bytes
from parsedwg.service import summarize_items


def test_parse_item_line_extracts_quantity_and_unit():
    item = parse_item_line("Кабель ВВГнг 3х1,5 - 120 м", source="drawing")

    assert item is not None
    assert item.name == "Кабель ВВГнг 3х1,5"
    assert item.quantity == 120
    assert item.unit == "м"
    assert item.section == "materials"


def test_summarize_items_groups_duplicates():
    items = [
        ParsedItem(name="Светильник LED", quantity=4, unit="шт", section="equipment", source="dwg"),
        ParsedItem(name="Светильник LED", quantity=2, unit="шт", section="equipment", source="note"),
    ]

    grouped = summarize_items(items)

    assert len(grouped) == 1
    assert grouped[0].quantity == 6
    assert grouped[0].source == "dwg, note"


def test_build_workbook_contains_required_sheets():
    items = [
        ParsedItem(name="Светильник LED", quantity=6, unit="шт", section="equipment", source="dwg"),
        ParsedItem(name="Монтаж кабеля", quantity=120, unit="м", section="works", source="dwg"),
    ]

    payload = build_workbook_bytes(items)
    workbook = load_workbook(BytesIO(payload))

    assert workbook.sheetnames == ["СО", "ВОР", "Смета", "Сводка"]
    assert workbook["СО"]["A2"].value == "Светильник LED"
    assert workbook["ВОР"]["A2"].value == "Монтаж кабеля"
