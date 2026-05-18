from pathlib import Path

import pytest

from parsedwg.process_source import parse_drawing
from src.parsedwg import errors


def test_process_source_uses_direct_pipeline_for_single_file(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "sample.dxf"
    source.write_text("stub", encoding="utf-8")

    processed_entry = {
        "kind": "file",
        "source": str(source),
        "name": source.name,
        "file_type": ".dxf",
        "parent_rel": "",
        "source_ref": str(source),
        "entity_md5": "abc",
        "summary": {"layouts": [], "blocks": [], "primitives": []},
    }
    captured: dict[str, object] = {}

    class FakeScalarResult:
        def scalar_one_or_none(self):
            return 77

    class FakeSession:
        def execute(self, _stmt):
            return FakeScalarResult()

    class FakeSessionContext:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_process_batch(batch):
        captured["batch"] = batch
        return [processed_entry]

    def fake_drawing_to_db(sources_path, processed_entries, project_id, detail_level):
        captured["sources_path"] = sources_path
        captured["processed_entries"] = list(processed_entries)
        captured["project_id"] = project_id
        captured["detail_level"] = detail_level
        return 7

    def fake_session_factory():
        return FakeSessionContext()

    monkeypatch.setattr("parsedwg.process_source.session_factory", fake_session_factory)
    monkeypatch.setattr("parsedwg.process_source.process_batch", fake_process_batch)
    monkeypatch.setattr("parsedwg.process_source.drawing_to_db", fake_drawing_to_db)

    result = parse_drawing(source, project_name="Sequential Project")

    assert result == {
        "job_id": None,
        "project_id": 77,
        "file_count": 1,
        "workers": 1,
        "mode": "direct",
        "detail_level": "high",
        "created_entities": 7,
    }
    assert captured["project_id"] == 77
    assert captured["detail_level"] == "high"
    assert captured["processed_entries"] == [processed_entry]


def test_process_source_raises_for_empty_directory_with_no_drawings(tmp_path: Path, monkeypatch) -> None:
    class FakeScalarResult:
        def scalar_one_or_none(self):
            return 77

    class FakeSession:
        def execute(self, _stmt):
            return FakeScalarResult()

    class FakeSessionContext:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_session_factory():
        return FakeSessionContext()

    monkeypatch.setattr("parsedwg.process_source.session_factory", fake_session_factory)

    with pytest.raises(errors.FileNotFound):
        parse_drawing(tmp_path, project_name="Sequential Project")


def test_process_source_dry_skips_db_and_project_lookup(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "sample.dxf"
    source.write_text("stub", encoding="utf-8")

    processed_entry = {
        "kind": "file",
        "source": str(source),
        "name": source.name,
        "file_type": ".dxf",
        "parent_rel": "",
        "source_ref": str(source),
        "entity_md5": "abc",
        "summary": {"layouts": [], "blocks": [], "primitives": []},
    }
    captured: dict[str, object] = {}

    def fake_process_batch(batch):
        captured["batch"] = batch
        return [processed_entry]

    def fake_session_factory():
        raise AssertionError("session_factory should not be used in dry mode")

    def fake_drawing_to_db(_sources_path, _processed_entries, project_id, detail_level):
        raise AssertionError(f"drawing_to_db should not be called in dry mode: {project_id}")

    monkeypatch.setattr("parsedwg.process_source.session_factory", fake_session_factory)
    monkeypatch.setattr("parsedwg.process_source.process_batch", fake_process_batch)
    monkeypatch.setattr("parsedwg.process_source.drawing_to_db", fake_drawing_to_db)

    result = parse_drawing(source, dry=True)

    assert result == {
        "job_id": None,
        "project_id": None,
        "file_count": 1,
        "workers": 1,
        "mode": "dry",
        "detail_level": "high",
        "created_entities": 0,
    }
    assert captured["batch"] == [
        {
            "kind": "file",
            "source": str(source),
            "name": source.name,
            "file_type": ".dxf",
            "parent_rel": "",
        }
    ]


def test_process_source_passes_detail_level_to_db(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "sample.dxf"
    source.write_text("stub", encoding="utf-8")

    processed_entry = {
        "kind": "file",
        "source": str(source),
        "name": source.name,
        "file_type": ".dxf",
        "parent_rel": "",
        "source_ref": str(source),
        "entity_md5": "abc",
        "summary": {"layouts": [], "blocks": [], "primitives": []},
    }
    captured: dict[str, object] = {}

    class FakeScalarResult:
        def scalar_one_or_none(self):
            return 77

    class FakeSession:
        def execute(self, _stmt):
            return FakeScalarResult()

    class FakeSessionContext:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_process_batch(_batch):
        return [processed_entry]

    def fake_drawing_to_db(_sources_path, processed_entries, project_id, detail_level):
        captured["processed_entries"] = list(processed_entries)
        captured["project_id"] = project_id
        captured["detail_level"] = detail_level
        return 7

    def fake_session_factory():
        return FakeSessionContext()

    monkeypatch.setattr("parsedwg.process_source.session_factory", fake_session_factory)
    monkeypatch.setattr("parsedwg.process_source.process_batch", fake_process_batch)
    monkeypatch.setattr("parsedwg.process_source.drawing_to_db", fake_drawing_to_db)

    result = parse_drawing(source, project_name="Sequential Project", detail_level="medium")

    assert result["detail_level"] == "medium"
    assert captured["detail_level"] == "medium"