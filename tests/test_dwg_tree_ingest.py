from pathlib import Path
from zipfile import ZipFile

from ezdxf.filemanagement import new

from parsedwg.dwg_tree_ingest import DWGTreeProcessor
from parsedwg.dwg_tree_ingest import _describe_entity
from parsedwg.dwg_tree_ingest import collect_dxf_summary


def test_discover_dwg_sources_finds_regular_and_zipped_dwg(tmp_path: Path) -> None:
    root = tmp_path / "tower"
    nested = root / "nested"
    nested.mkdir(parents=True)

    regular_dwg = nested / "plan.dwg"
    regular_dwg.write_bytes(b"dwg")

    zip_path = root / "archive.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("inside/a/model.dwg", b"dwg")
        archive.writestr("inside/a/readme.txt", b"txt")

    entries = list(DWGTreeProcessor(root).walk(root))

    assert len(entries) == 2

    kinds = sorted(entry["kind"] for entry in entries)
    assert kinds == ["file", "zipped_file"]

    file_entry = next(entry for entry in entries if entry["kind"] == "file")
    zipped_entry = next(entry for entry in entries if entry["kind"] == "zipped_file")

    assert file_entry["source"] == str(regular_dwg)
    assert zipped_entry["source"] == str(zip_path)
    assert zipped_entry["member"] == "inside/a/model.dwg"


def test_describe_entity_includes_lwpolyline_points() -> None:
    doc = new()
    polyline = doc.modelspace().add_lwpolyline([(10.0, 20.0), (30.0, 40.0)])

    description = _describe_entity(polyline)

    assert "type=LWPOLYLINE" in description
    assert "points=[(10.00, 20.00, 0.00), (30.00, 40.00, 0.00)]" in description


def test_compute_md5_hex_returns_32_char_hash(tmp_path: Path) -> None:
    source = tmp_path / "sample.dwg"
    source.write_bytes(b"abc")

    digest = DWGTreeProcessor.file_md5(source)

    assert digest == "900150983cd24fb0d6963f7d28e17f72"


def test_collect_dxf_summary_includes_text_primitives(tmp_path: Path) -> None:
    source = tmp_path / "sample.dxf"

    doc = new()
    doc.modelspace().add_text("Подпись", dxfattribs={"insert": (1, 2, 0), "layer": "TEXT"})
    sheet = doc.layouts.new("Sheet1")
    mtext = sheet.add_mtext("Многострочный\\Pтекст", dxfattribs={"layer": "NOTES"})
    mtext.dxf.insert = (3, 4, 0)
    doc.saveas(source)

    summary = collect_dxf_summary(source)
    primitives = summary["primitives"]

    assert len(primitives) == 2
    assert any(
        primitive["type"] == "TEXT"
        and primitive["text"] == "Подпись"
        and primitive["location"] == "(1.00, 2.00, 0.00)"
        for primitive in primitives
    )
    assert any(
        primitive["type"] == "MTEXT"
        and primitive["text"] == "Многострочный текст"
        and primitive["location"] == "(3.00, 4.00, 0.00)"
        and primitive["layout"] == "Sheet1"
        for primitive in primitives
    )


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