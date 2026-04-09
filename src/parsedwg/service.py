from __future__ import annotations

from pathlib import Path

from .models import ParsedItem
from .parsers import parse_drawing_file, parse_note_file
from .reporting import build_workbook_bytes

SECTION_ORDER = {"equipment": 0, "materials": 1, "works": 2}


def summarize_items(items: list[ParsedItem]) -> list[ParsedItem]:
    grouped: dict[tuple[str, str, str], ParsedItem] = {}

    for item in items:
        key = (item.name.casefold(), item.unit.casefold(), item.section)
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = ParsedItem(
                name=item.name,
                quantity=item.quantity,
                unit=item.unit,
                section=item.section,
                source=item.source,
                note=item.note,
                unit_price=item.unit_price,
            )
            continue

        existing.quantity += item.quantity
        existing.note = "; ".join(part for part in {existing.note, item.note} if part)
        sources = sorted({*existing.source.split(", "), *item.source.split(", ")})
        existing.source = ", ".join(source for source in sources if source)

    return sorted(grouped.values(), key=lambda item: (SECTION_ORDER.get(item.section, 9), item.name))


def generate_report_bytes(
    drawing_path: str | Path,
    note_path: str | Path | None = None,
) -> tuple[bytes, list[ParsedItem]]:
    items = parse_drawing_file(drawing_path)
    if note_path is not None:
        items.extend(parse_note_file(note_path))

    summarized = summarize_items(items)
    payload = build_workbook_bytes(summarized)
    return payload, summarized


def generate_report_file(
    drawing_path: str | Path,
    note_path: str | Path | None,
    output_path: str | Path,
) -> Path:
    payload, _ = generate_report_bytes(drawing_path, note_path)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return target
