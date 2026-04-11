import json

from ezdxf.filemanagement import new

from parsedwg.cli import main


def test_main_list_layouts_prints_table_for_single_file(tmp_path, capsys) -> None:
    source_path = tmp_path / "layouts.dxf"

    doc = new()
    doc.layers.add("MODEL_NOTES")
    doc.layers.add("SHEET_NOTES")
    doc.modelspace().add_text("Модель", dxfattribs={"layer": "MODEL_NOTES"})
    sheet = doc.layouts.new("Sheet1")
    sheet.add_text("Лист", dxfattribs={"layer": "SHEET_NOTES"})
    doc.saveas(source_path)

    exit_code = main(["list-layouts", str(source_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Sheet1" in captured.out
    assert "layout" in captured.out.lower()
    assert "layers" in captured.out.lower()
    assert "MODEL_NOTES" in captured.out
    assert "SHEET_NOTES" in captured.out


def test_main_list_layouts_converts_dwg_before_reading(tmp_path, monkeypatch, capsys) -> None:
    source_path = tmp_path / "layouts.dwg"
    converted_path = tmp_path / "layouts.converted.dxf"

    doc = new()
    doc.layouts.new("Sheet1")
    doc.saveas(converted_path)
    source_path.write_bytes(b"stub")

    monkeypatch.setattr("parsedwg.explorer._convert_dwg_to_dxf", lambda path: converted_path)

    exit_code = main(["list-layouts", str(source_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Sheet1" in captured.out
    assert "layout" in captured.out.lower()


def test_main_list_blocks_writes_json_for_single_file(tmp_path) -> None:
    source_path = tmp_path / "blocks.dxf"
    output_path = tmp_path / "result.json"

    doc = new()
    doc.blocks.new("BLOCK_A")
    doc.saveas(source_path)

    exit_code = main(["list-blocks", str(source_path), "-o", str(output_path)])

    assert exit_code == 0
    assert output_path.exists()
    rows = json.loads(output_path.read_text(encoding="utf-8"))
    assert any(row["block"] == "BLOCK_A" for row in rows)


def test_main_list_blocks_recurses_directory_and_creates_output_dir(tmp_path) -> None:
    source_dir = tmp_path / "drawings"
    nested_dir = source_dir / "nested"
    nested_dir.mkdir(parents=True)

    first_path = source_dir / "one.dxf"
    first_doc = new()
    first_doc.blocks.new("BLOCK_ONE")
    first_doc.saveas(first_path)

    second_path = nested_dir / "two.dxf"
    second_doc = new()
    second_doc.blocks.new("BLOCK_TWO")
    second_doc.saveas(second_path)

    output_dir = tmp_path / "json-output"
    exit_code = main(["list-blocks", str(source_dir), "-o", str(output_dir)])

    assert exit_code == 0
    assert output_dir.exists()

    first_json = output_dir / "one.json"
    second_json = output_dir / "nested" / "two.json"
    assert first_json.exists()
    assert second_json.exists()

    first_rows = json.loads(first_json.read_text(encoding="utf-8"))
    second_rows = json.loads(second_json.read_text(encoding="utf-8"))
    assert any(row["block"] == "BLOCK_ONE" for row in first_rows)
    assert any(row["block"] == "BLOCK_TWO" for row in second_rows)
