from pathlib import Path

from ezdxf.filemanagement import new

from parsedwg.dxf_analyzer import DXFAnalyzer
from parsedwg.process_source import collect_drawing_summary, collect_dxf_summary
from src.parsedwg.constants import EntityType


def test_describe_entity_includes_lwpolyline_points() -> None:
    doc = new()
    parent = doc.modelspace()
    polyline = parent.add_lwpolyline([(10.0, 20.0), (30.0, 40.0)])

    entity_data = DXFAnalyzer.get_entity_data(polyline, parent)

    assert entity_data["type"] == EntityType.LWPOLYLINE
    assert entity_data["parent"] is parent
    assert entity_data["points"] == [[10.0, 20.0, 0.0], [30.0, 40.0, 0.0]]


def test_collect_dxf_summary_includes_text_primitives(tmp_path: Path) -> None:
    source = tmp_path / "sample.dxf"

    doc = new()
    model = doc.modelspace()
    model.add_text("Подпись", dxfattribs={"insert": (1, 2, 0), "layer": "TEXT"})
    sheet = doc.layouts.new("Sheet1")
    mtext = sheet.add_mtext("Многострочный\\Pтекст", dxfattribs={"layer": "NOTES"})
    mtext.dxf.insert = (3, 4, 0)
    doc.saveas(source)

    summary = collect_dxf_summary(source)
    primitives = summary["primitives"]

    assert len(primitives) == 2
    assert any(
        primitive["type"] == EntityType.TEXT
        and primitive["description"] == "Подпись"
        and primitive["dxf_attribs"]["insert"] == [1.0, 2.0, 0.0]
        and primitive["layout"].name == "Model"
        for primitive in primitives
    )
    assert any(
        primitive["type"] == EntityType.MTEXT
        and primitive["description"] == "Многострочный текст"
        and primitive["dxf_attribs"]["insert"] == [3.0, 4.0, 0.0]
        and primitive["layout"].name == "Sheet1"
        for primitive in primitives
    )


def test_collect_dxf_summary_includes_insert_primitives_from_layouts(tmp_path: Path) -> None:
    source = tmp_path / "sample-layout-insert.dxf"

    doc = new()
    doc.blocks.new("MARKER")
    doc.modelspace().add_blockref("MARKER", (5, 6, 0), dxfattribs={"layer": "A-INSERTS"})
    sheet = doc.layouts.new("Sheet1")
    sheet.add_blockref("MARKER", (7, 8, 0), dxfattribs={"layer": "S-INSERTS"})
    doc.saveas(source)

    summary = collect_dxf_summary(source)
    primitives = [
        primitive
        for primitive in summary["primitives"]
        if primitive.get("type") == EntityType.INSERT and primitive.get("target_block") == "MARKER"
    ]

    assert len(primitives) == 2
    assert any(
        primitive["layout"].name == "Model"
        and primitive["layer"] == "A-INSERTS"
        and primitive["dxf_attribs"]["insert"] == [5.0, 6.0, 0.0]
        for primitive in primitives
    )
    assert any(
        primitive["layout"].name == "Sheet1"
        and primitive["layer"] == "S-INSERTS"
        and primitive["dxf_attribs"]["insert"] == [7.0, 8.0, 0.0]
        for primitive in primitives
    )


def test_collect_drawing_summary_includes_layout_multileader_primitives(monkeypatch) -> None:
    class FakeDxfNamespace:
        layer = "A-ANNO"

        @staticmethod
        def hasattr(name: str) -> bool:
            return hasattr(FakeDxfNamespace, name)

    class FakeEntity:
        dxf = FakeDxfNamespace()

        @staticmethod
        def dxftype() -> str:
            return "MULTILEADER"

    class FakeLayout:
        def __init__(self, name: str, is_modelspace: bool = False):
            self.name = name
            self.is_modelspace = is_modelspace
            self.dxf = {"taborder": 0}

        def __iter__(self):
            return iter([FakeEntity()])

        def __len__(self):
            return 1

    class FakeDoc:
        def __init__(self):
            self.layouts = [FakeLayout("Model", is_modelspace=True)]
            self.layers = []
            self.blocks = []

    monkeypatch.setattr(
        "parsedwg.process_source.DXFAnalyzer.get_entity_data",
        lambda entity, parent=None, layout=None: {
            "type": entity.dxftype(),
            "block": None,
            "layer": "A-ANNO",
            "layout": layout.name if layout is not None else "Model",
            "parent_block": getattr(parent, "name", "Model") if parent is not None else "Model",
        },
    )

    summary = collect_drawing_summary(FakeDoc())

    assert summary["primitives"] == [
        {
            "type": "MULTILEADER",
            "block": None,
            "layer": "A-ANNO",
            "layout": "Model",
            "parent_block": "Model",
        }
    ]


def test_collect_dxf_summary_marks_table_blocks_and_keeps_table_data(tmp_path: Path) -> None:
    source = tmp_path / "table-block.dxf"

    doc = new()
    block = doc.blocks.new("TABLE_A")
    block.add_text("H1", dxfattribs={"insert": (0, 20, 0)})
    block.add_text("H2", dxfattribs={"insert": (50, 20, 0)})
    block.add_text("R1C1", dxfattribs={"insert": (0, 10, 0)})
    block.add_text("R1C2", dxfattribs={"insert": (50, 10, 0)})
    block.add_text("R2C1", dxfattribs={"insert": (0, 0, 0)})
    block.add_text("R2C2", dxfattribs={"insert": (50, 0, 0)})
    doc.saveas(source)

    summary = collect_dxf_summary(source)
    table_block = next(item for item in summary["blocks"] if item["name"] == "TABLE_A")

    assert table_block["is_table"] is True
    table_data = table_block["table"]
    assert table_data["rows"] == [["H1", "H2"], ["R1C1", "R1C2"], ["R2C1", "R2C2"]]
    assert table_data["x_clusters"] >= 2
    assert table_data["y_clusters"] >= 2