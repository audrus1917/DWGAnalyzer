import dataclasses
from pathlib import Path

import ezdxf

from dwganalyzer.io import load_drawing
from dwganalyzer.models import AttributeDefinition, AttributeValue
from dwganalyzer.parsers import parse_drawing


def test_parses_layouts_and_layers() -> None:
    drawing = ezdxf.new()
    drawing.layers.add(
        "NOTES",
        color=3,
        linetype="DASHED",
    )
    drawing.layouts.new("Sheet A")
    drawing.modelspace().add_line((0, 0), (10, 10), dxfattribs={"layer": "NOTES"})

    summary = parse_drawing(drawing, source="drawing.dxf")

    assert summary.source == "drawing.dxf"
    assert [(layout.name, layout.is_modelspace) for layout in summary.layouts] == [
        ("Model", True),
        ("Layout1", False),
        ("Sheet A", False),
    ]
    notes = next(layer for layer in summary.layers if layer.name == "NOTES")
    assert notes.color == 3
    assert notes.linetype == "DASHED"
    assert notes.is_on is True
    assert summary.entity_count == 1


def test_normalizes_text_entities() -> None:
    drawing = ezdxf.new()
    modelspace = drawing.modelspace()
    modelspace.add_text("  Equipment   room  ", dxfattribs={"layer": "NOTES"})
    modelspace.add_mtext("First line\\PSecond line")

    summary = parse_drawing(drawing, source="drawing.dxf")

    assert [entity.entity_type for entity in summary.entities] == ["TEXT", "MTEXT"]
    assert [entity.text for entity in summary.entities] == [
        "Equipment room",
        "First line Second line",
    ]
    assert summary.entities[0].layout == "Model"
    assert summary.entities[0].layer == "NOTES"


def test_parses_blocks_and_inserts() -> None:
    drawing = ezdxf.new()
    nested = drawing.blocks.new("NESTED")
    nested.add_line((0, 0), (1, 1), dxfattribs={"layer": "DETAILS"})
    block = drawing.blocks.new("DEVICE")
    block.add_text("Device label", dxfattribs={"layer": "LABELS"})
    block.add_attdef(
        "MARK",
        insert=(0, 0),
        text="Unknown",
        dxfattribs={"prompt": "Device mark"},
    )
    block.add_blockref("NESTED", (0, 0))
    insert = drawing.modelspace().add_blockref("DEVICE", (10, 20))
    insert.add_attrib("MARK", "A-01", insert=(10, 20))

    summary = parse_drawing(drawing, source="drawing.dxf")

    device = next(block for block in summary.blocks if block.name == "DEVICE")
    assert device.entity_count == 3
    assert device.layers == ("LABELS", "0")
    assert device.nested_blocks == ("NESTED",)
    assert device.text == ("Device label",)
    assert device.attribute_definitions == (
        AttributeDefinition("MARK", "Device mark", "Unknown"),
    )

    entity = summary.entities[0]
    assert entity.entity_type == "INSERT"
    assert entity.block_name == "DEVICE"
    assert entity.attributes == (AttributeValue("MARK", "A-01"),)


def test_does_not_expose_or_mutate_entities() -> None:
    drawing = ezdxf.new()
    line = drawing.modelspace().add_line((1, 2, 3), (4, 5, 6))

    summary = parse_drawing(drawing, source="drawing.dxf")

    assert dataclasses.is_dataclass(summary.entities[0])
    assert not hasattr(summary.entities[0], "dxf")
    assert line.dxf.start == (1, 2, 3)
    assert line.dxf.end == (4, 5, 6)


def test_parses_loaded_dxf(tmp_path: Path) -> None:
    source = tmp_path / "drawing.dxf"
    drawing = ezdxf.new()
    drawing.modelspace().add_circle((5, 5), radius=2)
    drawing.saveas(source)

    summary = parse_drawing(load_drawing(source), source=str(source))

    assert summary.source == str(source)
    assert summary.entity_count == 1
    assert summary.entities[0].entity_type == "CIRCLE"
