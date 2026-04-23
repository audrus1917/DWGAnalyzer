from pathlib import Path
from zipfile import ZipFile

from ezdxf.filemanagement import new

from parsedwg.process_tree import DWGTreeProcessor
from parsedwg.process_tree import get_entity_data
from parsedwg.process_tree import collect_dxf_summary
from parsedwg.process_tree import run_process_tree


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

    description = get_entity_data(polyline)

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
    block_text = doc.blocks.new("TEXT_BLOCK")
    block_text.add_text("Подпись", dxfattribs={"insert": (1, 2, 0), "layer": "TEXT"})
    block_notes = doc.blocks.new("NOTES_BLOCK")
    mtext = block_notes.add_mtext("Многострочный\\Pтекст", dxfattribs={"layer": "NOTES"})
    mtext.dxf.insert = (3, 4, 0)
    doc.saveas(source)

    summary = collect_dxf_summary(source)
    primitives = summary["primitives"]

    assert len(primitives) == 2
    assert any(
        primitive["type"] == "TEXT"
        and primitive["text"] == "Подпись"
        and primitive["location"] == "(1.00, 2.00, 0.00)"
        and primitive["block"] == "TEXT_BLOCK"
        for primitive in primitives
    )
    assert any(
        primitive["type"] == "MTEXT"
        and primitive["text"] == "Многострочный текст"
        and primitive["location"] == "(3.00, 4.00, 0.00)"
        and primitive["block"] == "NOTES_BLOCK"
        for primitive in primitives
    )


def test_collect_dxf_summary_enriches_primitives_with_ai_name_tags(tmp_path: Path) -> None:
    source = tmp_path / "sample-ai-tags.dxf"

    doc = new()
    block = doc.blocks.new("ROOF_BLOCK")
    block.add_text("Кровля", dxfattribs={"insert": (1, 2, 0), "layer": "TEXT"})
    doc.saveas(source)

    class StubTagsExtractor:
        def extract(self, text: str) -> list[str]:
            if text == "Кровля":
                return ["кровля", "кровля", "раздел"]
            return []

    summary = collect_dxf_summary(source, name_tags_extractor=StubTagsExtractor())
    primitives = summary["primitives"]

    assert len(primitives) == 1
    assert primitives[0]["text"] == "Кровля"
    assert primitives[0]["block"] == "ROOF_BLOCK"
    assert primitives[0]["ai_name_tags"] == ["кровля", "раздел"]


def test_collect_dxf_summary_includes_insert_primitives_for_blocks(tmp_path: Path) -> None:
    source = tmp_path / "sample-insert.dxf"

    doc = new()
    doc.blocks.new("MARKER")
    container = doc.blocks.new("CONTAINER")
    container.add_blockref("MARKER", (10, 20, 0), dxfattribs={"layer": "INSERTS"})
    doc.saveas(source)

    summary = collect_dxf_summary(source)
    primitives = summary["primitives"]

    assert len(primitives) == 1
    assert primitives[0]["type"] == "INSERT"
    assert primitives[0]["block"] == "CONTAINER"
    assert primitives[0]["target_block"] == "MARKER"
    assert primitives[0]["text"] == "MARKER"
    assert primitives[0]["location"] == "(10.00, 20.00, 0.00)"
    assert primitives[0]["layer"] == "INSERTS"


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
        if primitive["type"] == "INSERT" and primitive["target_block"] == "MARKER"
    ]

    assert len(primitives) == 2
    assert any(
        primitive["layout"] == "Model"
        and primitive["layer"] == "A-INSERTS"
        and primitive["location"] == "(5.00, 6.00, 0.00)"
        for primitive in primitives
    )
    assert any(
        primitive["layout"] == "Sheet1"
        and primitive["layer"] == "S-INSERTS"
        and primitive["location"] == "(7.00, 8.00, 0.00)"
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


def test_run_process_tree_supports_sequential_mode(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "sample.dxf"
    source.write_text("stub", encoding="utf-8")

    processed_entry = {
        "kind": "file",
        "source": str(source),
        "name": source.name,
        "file_type": ".dxf",
        "parent_rel": "",
        "source_ref": str(source),
        "file_md5": "abc",
        "summary": {"layouts": [], "blocks": [], "primitives": []},
    }

    captured: dict[str, object] = {}

    monkeypatch.setattr("parsedwg.process_tree.new_job_id", lambda: "job-1")
    monkeypatch.setattr("parsedwg.process_tree.push_sources", lambda _job_id, _entries: None)
    monkeypatch.setattr("parsedwg.process_tree.load_converted", lambda _job_id: [processed_entry])
    monkeypatch.setattr("parsedwg.process_tree.get_workers_number", lambda _workers: 1)

    def fake_process_batch(batch, processed_queue=None, job_id=None, name_tags_config=None):
        _ = (batch, name_tags_config)
        captured["job_id"] = job_id
        captured["queue"] = processed_queue
        if processed_queue is not None:
            processed_queue.put(processed_entry)
            processed_queue.put({"__queue_event__": "worker_done"})
        return [processed_entry]

    def fake_process_queue(
        processed_queue,
        root_path,
        producer_count,
        project_name,
        project_description,
        created_by,
    ):
        _ = (processed_queue, project_description, created_by)
        captured["root_path"] = root_path
        captured["producer_count"] = producer_count
        captured["project_name"] = project_name
        return ("project-1", 7)

    monkeypatch.setattr("parsedwg.process_tree._process_batch", fake_process_batch)
    monkeypatch.setattr("parsedwg.process_tree.process_queue", fake_process_queue)

    result = run_process_tree(
        source,
        conversion_workers=3,
        project_name="Sequential Project",
        use_process_pool=False,
    )

    assert result["project_id"] == "project-1"
    assert result["file_count"] == 1
    assert result["processed_count"] == 1
    assert result["workers"] == 1
    assert result["created_entities"] == 7
    assert captured["job_id"] == "job-1"
    assert captured["producer_count"] == 1
    assert captured["project_name"] == "Sequential Project"