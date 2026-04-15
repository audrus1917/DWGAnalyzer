from pathlib import Path
from zipfile import ZipFile

from ezdxf.filemanagement import new

from parsedwg.dwg_tree_ingest import discover_dwg_sources
from parsedwg.dwg_tree_ingest import _describe_entity


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

    entries = discover_dwg_sources(root)

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