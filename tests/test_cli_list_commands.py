import json
from pathlib import Path

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
    source_path.write_bytes(b"stub")

    doc = new()
    doc.layouts.new("Sheet1")

    captured_args: dict[str, object] = {}

    def fake_read_odafc(path, version):
        captured_args["path"] = path
        captured_args["version"] = version
        return doc

    monkeypatch.setattr("parsedwg.explorer.read_odafc", fake_read_odafc)

    exit_code = main(["list-layouts", str(source_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_args["path"] == source_path
    assert captured_args["version"] == "ACAD2018"
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


def test_main_extract_name_tags_recurses_and_writes_json(tmp_path) -> None:
    source_dir = tmp_path / "tower_A"
    nested_dir = source_dir / "nested"
    nested_dir.mkdir(parents=True)

    roof_file = source_dir / "План кровли.dwg"
    floor_file = nested_dir / "ПЛАН_ЭО_6-9 эт..dwg"
    roof_file.write_text("stub", encoding="utf-8")
    floor_file.write_text("stub", encoding="utf-8")

    output_path = tmp_path / "name-tags.json"
    exit_code = main(["extract-name-tags", str(source_dir), "-o", str(output_path)])

    assert exit_code == 0
    assert output_path.exists()

    rows = json.loads(output_path.read_text(encoding="utf-8"))
    indexed = {Path(row["file"]).name: row for row in rows}
    assert indexed["План кровли.dwg"]["entities"] == ["Кровля"]
    assert indexed["ПЛАН_ЭО_6-9 эт..dwg"]["entities"] == [
        "6-й этаж",
        "7-й этаж",
        "8-й этаж",
        "9-й этаж",
    ]


def test_main_ingest_dwg_tree_runs_pipeline(tmp_path, monkeypatch, capsys) -> None:
    source_dir = tmp_path / "tower_A"
    source_dir.mkdir(parents=True)

    captured_args: dict[str, object] = {}

    def fake_run(source_path: Path, conversion_workers: int = 2) -> dict[str, object]:
        captured_args["source_path"] = source_path
        captured_args["conversion_workers"] = conversion_workers
        return {
            "source_list": "/tmp/sources.json",
            "converted_list": "/tmp/converted.json",
            "dwg_count": 3,
            "dxf_count": 3,
            "created_entities": 42,
        }

    monkeypatch.setattr("parsedwg.cli.run_dwg_tree_ingest", fake_run)

    exit_code = main(["ingest-dwg-tree", str(source_dir), "--workers", "2"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_args["source_path"] == source_dir
    assert captured_args["conversion_workers"] == 2
    assert "Найдено DWG: 3" in captured.out
    assert "Сконвертировано DXF: 3" in captured.out
    assert "Создано сущностей в БД: 42" in captured.out


def test_main_search_passes_parent_id_to_search_entities(monkeypatch) -> None:
    captured_kwargs: dict = {}

    async def fake_search(query, entity_type=None, limit=20, parent_id=None):
        captured_kwargs["query"] = query
        captured_kwargs["entity_type"] = entity_type
        captured_kwargs["limit"] = limit
        captured_kwargs["parent_id"] = parent_id
        return []

    monkeypatch.setattr("parsedwg.db.search_entities", fake_search)

    pid = "11111111-1111-1111-1111-111111111111"
    exit_code = main(["search", "блок", "--parent-id", pid, "--limit", "5"])

    assert exit_code == 0
    assert captured_kwargs["query"] == "блок"
    assert captured_kwargs["parent_id"] == pid
    assert captured_kwargs["limit"] == 5
    assert captured_kwargs["entity_type"] is None


def test_main_ingest_docs_runs_pipeline(tmp_path, monkeypatch, capsys) -> None:
    source_dir = tmp_path / "docs"
    source_dir.mkdir(parents=True)

    captured_args: dict[str, object] = {}

    def fake_run(source_path: Path) -> dict[str, object]:
        captured_args["source_path"] = source_path
        return {
            "doc_count": 4,
            "created_entities": 4,
            "source": str(source_path),
        }

    monkeypatch.setattr("parsedwg.cli.run_documents_ingest", fake_run)

    exit_code = main(["ingest-docs", str(source_dir)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_args["source_path"] == source_dir
    assert "Найдено документов: 4" in captured.out
    assert "Создано сущностей в БД: 4" in captured.out
