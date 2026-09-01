import ezdxf

from dwganalyzer.models import (
    AttributeValue,
    BlockSummary,
    DrawingSummary,
    EntitySummary,
    LayerSummary,
    LayoutSummary,
    NamedCount,
)
from dwganalyzer.parsers import parse_drawing
from dwganalyzer.services import analyze_drawing


def _layer(name: str) -> LayerSummary:
    return LayerSummary(
        name=name,
        color=7,
        linetype="Continuous",
        lineweight=-3,
        is_on=True,
        is_frozen=False,
        is_locked=False,
    )


def test_builds_drawing_inventory() -> None:
    summary = DrawingSummary(
        source="drawing.dxf",
        layouts=(LayoutSummary("Model", True, 0, 3),),
        layers=(_layer("NOTES"), _layer("EQUIPMENT")),
        blocks=(BlockSummary("DEVICE", 1),),
        entities=(
            EntitySummary("TEXT", "Model", layer="NOTES", text="Room"),
            EntitySummary(
                "INSERT",
                "Model",
                layer="EQUIPMENT",
                block_name="DEVICE",
                attributes=(AttributeValue("MARK", "A-01"),),
            ),
            EntitySummary("LINE", "Model", layer="EQUIPMENT"),
        ),
        entity_count=3,
    )

    analysis = analyze_drawing(summary)

    assert analysis.source == "drawing.dxf"
    assert analysis.entity_count == 3
    assert analysis.layout_count == 1
    assert analysis.layer_count == 2
    assert analysis.block_definition_count == 1
    assert analysis.text_entity_count == 1
    assert analysis.block_reference_count == 1
    assert analysis.attributed_block_reference_count == 1
    assert analysis.attribute_count == 1
    assert analysis.entity_types == (
        NamedCount("INSERT", 1),
        NamedCount("LINE", 1),
        NamedCount("TEXT", 1),
    )
    assert analysis.entities_by_layer == (
        NamedCount("EQUIPMENT", 2),
        NamedCount("NOTES", 1),
    )
    assert analysis.block_references == (NamedCount("DEVICE", 1),)
    assert analysis.findings == ()


def test_analyzes_block_reachability() -> None:
    summary = DrawingSummary(
        source="drawing.dxf",
        layouts=(LayoutSummary("Model", True, 0, 1),),
        layers=(_layer("0"),),
        blocks=(
            BlockSummary("ROOT", 2, nested_blocks=("CHILD", "MISSING")),
            BlockSummary("CHILD", 1, nested_blocks=("ROOT",)),
            BlockSummary("ORPHAN", 0),
        ),
        entities=(
            EntitySummary("INSERT", "Model", layer="0", block_name="ROOT"),
        ),
        entity_count=1,
    )

    analysis = analyze_drawing(summary)

    assert analysis.used_blocks == ("CHILD", "ROOT")
    assert analysis.unused_blocks == ("ORPHAN",)
    assert analysis.missing_blocks == ("MISSING",)
    assert [finding.code for finding in analysis.findings] == [
        "missing_block_definition"
    ]
    assert analysis.findings[0].subject == "MISSING"


def test_reports_structure_findings() -> None:
    summary = DrawingSummary(
        source="inconsistent.dxf",
        layouts=(LayoutSummary("Model", True, 0, 0),),
        layers=(_layer("0"),),
        entities=(
            EntitySummary(
                "INSERT",
                "Missing layout",
                layer="MISSING",
                block_name="MISSING",
            ),
        ),
        entity_count=2,
    )

    analysis = analyze_drawing(summary)

    assert analysis.entities_without_layer == 0
    assert [(finding.code, finding.subject) for finding in analysis.findings] == [
        ("entity_count_mismatch", None),
        ("missing_layout_definition", "Missing layout"),
        ("missing_layer_definition", "MISSING"),
        ("missing_block_definition", "MISSING"),
    ]
    assert analysis.findings[0].expected_count == 2
    assert analysis.findings[0].actual_count == 1


def test_reports_empty_drawing() -> None:
    analysis = analyze_drawing(DrawingSummary(source="empty.dxf"))

    assert analysis.entity_count == 0
    assert [finding.code for finding in analysis.findings] == ["empty_drawing"]


def test_analyzes_parsed_drawing() -> None:
    drawing = ezdxf.new()
    drawing.blocks.new("DEVICE")
    drawing.modelspace().add_blockref("DEVICE", (0, 0))
    drawing.modelspace().add_text("Device")

    summary = parse_drawing(drawing, source="drawing.dxf")
    analysis = analyze_drawing(summary)

    assert analysis.entity_count == 2
    assert analysis.block_references == (NamedCount("DEVICE", 1),)
    assert analysis.used_blocks == ("DEVICE",)
    assert analysis.text_entity_count == 1
    assert analysis.findings == ()
