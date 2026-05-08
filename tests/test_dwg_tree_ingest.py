import asyncio
from pathlib import Path
import uuid
from zipfile import ZipFile

from ezdxf.filemanagement import new

from parsedwg.process_source import DWGTreeProcessor
from parsedwg.process_source import collect_dxf_summary
from parsedwg.process_source import collect_drawing_summary
from parsedwg.process_source import process_source
from parsedwg.process_source import drawing_to_db
from parsedwg.dxf_analyzer import DXFAnalyzer
from parsedwg.orm import Entity
from parsedwg.orm import EntityType
from parsedwg.orm import Primitive


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

    entity_data = DXFAnalyzer.get_entity_data(polyline)

    assert entity_data["type"] == "LWPOLYLINE"
    assert entity_data["block"] is None
    assert entity_data["points"] == [[10.0, 20.0, 0.0], [30.0, 40.0, 0.0]]


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
        and primitive["attribs"]["insert"] == [1.0, 2.0, 0.0]
        and primitive["block"] == "TEXT_BLOCK"
        for primitive in primitives
    )
    assert any(
        primitive["type"] == "MTEXT"
        and primitive["text"] == "Многострочный текст"
        and primitive["attribs"]["insert"] == [3.0, 4.0, 0.0]
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
    assert primitives[0]["block"] == "MARKER"
    assert primitives[0]["attribs"]["insert"] == [10.0, 20.0, 0.0]
    assert primitives[0]["attribs"]["insert"] == [10.0, 20.0, 0.0]
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
        if primitive.get("type") == "INSERT" and primitive.get("target_block") == "MARKER"
    ]

    assert len(primitives) == 2
    assert any(
        primitive["layout"] == "Model"
        and primitive["layer"] == "A-INSERTS"
        and primitive["location"] == "[5.0, 6.0, 0.0]"
        for primitive in primitives
    )
    assert any(
        primitive["layout"] == "Sheet1"
        and primitive["layer"] == "S-INSERTS"
        and primitive["location"] == "[7.0, 8.0, 0.0]"
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

    class FakeDoc:
        def __init__(self):
            self.layouts = [FakeLayout("Model", is_modelspace=True)]
            self.layers = []
            self.blocks = []

    monkeypatch.setattr("parsedwg.process_tree.iter_blocks", lambda drawing: iter([]))
    monkeypatch.setattr(
        "parsedwg.process_tree.DXFAnalyzer.get_entity_data",
        lambda entity, block=None: {
            "type": entity.dxftype(),
            "block": None,
            "layer": "A-ANNO",
        },
    )

    summary = collect_drawing_summary(FakeDoc())

    assert summary["primitives"] == [
        {
            "type": "MULTILEADER",
            "block": "Model",
            "layer": "A-ANNO",
            "layout": "Model",
            "parent_block": "Model",
        }
    ]


def test_save_tree_to_db_keeps_layout_primitives_without_block_entity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    processed_entry = {
        "kind": "file",
        "source": str(tmp_path / "sample.dxf"),
        "name": "sample.dxf",
        "file_type": ".dxf",
        "parent_rel": "",
        "source_ref": str(tmp_path / "sample.dxf"),
        "entity_md5": "abc",
        "summary": {
            "layouts": [{"name": "Model"}],
            "layers": [{"name": "A-ANNO", "data": {}}],
            "blocks": [],
            "primitives": [
                {
                    "type": "MULTILEADER",
                    "text": "Выноска",
                    "block": "Model",
                    "parent_block": "Model",
                    "layout": "Model",
                    "layer": "A-ANNO",
                }
            ],
        },
    }

    added_primitives = []

    class _FakeScalarResult:
        def scalar_one_or_none(self):
            return None

    class _FakeSession:
        def add(self, obj):
            if isinstance(obj, Entity):
                if obj.id is None:
                    obj.id = uuid.uuid4()
            if isinstance(obj, Primitive):
                if obj.id is None:
                    obj.id = uuid.uuid4()
                added_primitives.append(obj)

        def add_all(self, objects):
            for obj in objects:
                self.add(obj)

        async def flush(self):
            return None

        async def execute(self, _stmt):
            return _FakeScalarResult()

        async def commit(self):
            return None

    class _FakeSessionContext:
        async def __aenter__(self):
            return _FakeSession()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def _fake_async_session_factory():
        return _FakeSessionContext()

    monkeypatch.setattr(
        "parsedwg.process_tree.async_session_factory",
        _fake_async_session_factory,
    )

    asyncio.run(
        drawing_to_db(
            sources_path=str(tmp_path),
            processed_entries=[processed_entry],
            project_name="Test Project",
        )
    )

    assert any(primitive.entity_type == EntityType.MLEADER for primitive in added_primitives)


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


def test_collect_drawing_summary_uses_tqdm_with_block_count(monkeypatch) -> None:
    doc = new()
    doc.blocks.new("BLOCK_A")
    doc.blocks.new("BLOCK_B")

    captured: dict[str, object] = {}

    def fake_tqdm(iterable, **kwargs):
        captured["total"] = kwargs.get("total")
        captured["desc"] = kwargs.get("desc")
        captured["unit"] = kwargs.get("unit")
        captured["disable"] = kwargs.get("disable")
        return iterable

    monkeypatch.setattr("parsedwg.process_tree._tqdm", fake_tqdm)
    monkeypatch.setattr("parsedwg.process_tree.sys.stderr.isatty", lambda: True)

    collect_drawing_summary(doc)

    assert captured["total"] == len(list(doc.blocks))
    assert captured["desc"] == "Blocks"
    assert captured["unit"] == "block"
    assert captured["disable"] is False


def test_save_tree_to_db_sets_file_id_for_all_descendants(
    tmp_path: Path,
    monkeypatch,
) -> None:
    processed_entry = {
        "kind": "file",
        "source": str(tmp_path / "sample.dxf"),
        "name": "sample.dxf",
        "file_type": ".dxf",
        "parent_rel": "",
        "source_ref": str(tmp_path / "sample.dxf"),
        "entity_md5": "abc",
        "summary": {
            "layouts": [{"name": "Model"}],
            "layers": [{"name": "A-TEXT", "data": {}}],
            "blocks": [{"name": "BLOCK_A", "entity_count": 1, "is_table": False}],
            "primitives": [
                {
                    "type": "TEXT",
                    "text": "Подпись",
                    "block": "BLOCK_A",
                    "layout": "Model",
                    "layer": "A-TEXT",
                }
            ],
        },
    }

    added_entities: list[Entity] = []
    added_primitives: list[Primitive] = []

    class _FakeScalarResult:
        def scalar_one_or_none(self):
            return None

    class _FakeSession:
        def add(self, obj):
            if isinstance(obj, Entity):
                if obj.id is None:
                    obj.id = uuid.uuid4()
                added_entities.append(obj)
            if isinstance(obj, Primitive):
                if obj.id is None:
                    obj.id = uuid.uuid4()
                added_primitives.append(obj)

        def add_all(self, objects):
            for obj in objects:
                self.add(obj)

        async def flush(self):
            return None

        async def execute(self, _stmt):
            return _FakeScalarResult()

        async def commit(self):
            return None

    class _FakeSessionContext:
        async def __aenter__(self):
            return _FakeSession()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def fake_async_session_factory():
        return _FakeSessionContext()

    monkeypatch.setattr("parsedwg.process_tree.async_session_factory", fake_async_session_factory)

    asyncio.run(
        drawing_to_db(
            sources_path=str(tmp_path),
            processed_entries=[processed_entry],
            project_name="Test Project",
        )
    )

    file_entity = next(entity for entity in added_entities if entity.entity_type == EntityType.FILE)

    descendants = [
        entity
        for entity in added_entities
        if entity.entity_type in {
            EntityType.LAYOUT,
            EntityType.LAYER,
            EntityType.BLOCK,
        }
    ]

    assert descendants
    assert all(entity.file_id == file_entity.id for entity in descendants)
    assert added_primitives
    assert all(primitive.file_id == file_entity.id for primitive in added_primitives)


def test_save_tree_to_db_commits_primitives_in_batches(
    tmp_path: Path,
    monkeypatch,
) -> None:
    primitives = [
        {
            "type": "TEXT",
            "text": f"Подпись {index}",
            "block": "BLOCK_A",
            "layout": "Model",
            "layer": "A-TEXT",
        }
        for index in range(1001)
    ]
    processed_entry = {
        "kind": "file",
        "source": str(tmp_path / "sample.dxf"),
        "name": "sample.dxf",
        "file_type": ".dxf",
        "parent_rel": "",
        "source_ref": str(tmp_path / "sample.dxf"),
        "entity_md5": "abc",
        "summary": {
            "layouts": [{"name": "Model"}],
            "layers": [{"name": "A-TEXT", "data": {}}],
            "blocks": [{"name": "BLOCK_A", "entity_count": 1001, "is_table": False}],
            "primitives": primitives,
        },
    }

    commit_calls = 0
    primitive_entity_batch_sizes: list[int] = []

    class _FakeScalarResult:
        def scalar_one_or_none(self):
            return None

    class _FakeSession:
        def add(self, obj):
            if isinstance(obj, Entity) and obj.id is None:
                obj.id = uuid.uuid4()

        def add_all(self, objects):
            nonlocal primitive_entity_batch_sizes

            objects = list(objects)
            for obj in objects:
                self.add(obj)
            if objects and all(isinstance(obj, Primitive) for obj in objects):
                primitive_entity_batch_sizes.append(len(objects))

        async def flush(self):
            return None

        async def execute(self, _stmt):
            return _FakeScalarResult()

        async def commit(self):
            nonlocal commit_calls
            commit_calls += 1

    class _FakeSessionContext:
        async def __aenter__(self):
            return _FakeSession()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def fake_async_session_factory():
        return _FakeSessionContext()

    monkeypatch.setattr("parsedwg.process_tree.async_session_factory", fake_async_session_factory)

    asyncio.run(
        drawing_to_db(
            sources_path=str(tmp_path),
            processed_entries=[processed_entry],
            project_name="Test Project",
        )
    )

    assert primitive_entity_batch_sizes == [1000, 1]
    assert commit_calls == 2


def test_save_tree_to_db_uses_tqdm_for_primitives(
    tmp_path: Path,
    monkeypatch,
) -> None:
    processed_entry = {
        "kind": "file",
        "source": str(tmp_path / "sample.dxf"),
        "name": "sample.dxf",
        "file_type": ".dxf",
        "parent_rel": "",
        "source_ref": str(tmp_path / "sample.dxf"),
        "entity_md5": "abc",
        "summary": {
            "layouts": [{"name": "Model"}],
            "layers": [{"name": "A-TEXT", "data": {}}],
            "blocks": [{"name": "BLOCK_A", "entity_count": 2, "is_table": False}],
            "primitives": [
                {
                    "type": "TEXT",
                    "text": "Подпись 1",
                    "block": "BLOCK_A",
                    "layout": "Model",
                    "layer": "A-TEXT",
                },
                {
                    "type": "TEXT",
                    "text": "Подпись 2",
                    "block": "BLOCK_A",
                    "layout": "Model",
                    "layer": "A-TEXT",
                },
            ],
        },
    }

    captured: dict[str, object] = {}

    def fake_tqdm(iterable, **kwargs):
        captured["total"] = kwargs.get("total")
        captured["desc"] = kwargs.get("desc")
        captured["unit"] = kwargs.get("unit")
        captured["disable"] = kwargs.get("disable")
        return iterable

    class _FakeScalarResult:
        def scalar_one_or_none(self):
            return None

    class _FakeSession:
        def add(self, obj):
            if isinstance(obj, Entity) and obj.id is None:
                obj.id = uuid.uuid4()

        def add_all(self, objects):
            for obj in objects:
                self.add(obj)

        async def flush(self):
            return None

        async def execute(self, _stmt):
            return _FakeScalarResult()

        async def commit(self):
            return None

    class _FakeSessionContext:
        async def __aenter__(self):
            return _FakeSession()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def fake_async_session_factory():
        return _FakeSessionContext()

    monkeypatch.setattr("parsedwg.process_tree._tqdm", fake_tqdm)
    monkeypatch.setattr("parsedwg.process_tree.sys.stderr.isatty", lambda: True)
    monkeypatch.setattr("parsedwg.process_tree.async_session_factory", fake_async_session_factory)

    asyncio.run(
        drawing_to_db(
            sources_path=str(tmp_path),
            processed_entries=[processed_entry],
            project_name="Test Project",
        )
    )

    assert captured["total"] == 2
    assert captured["desc"] == "Primitives"
    assert captured["unit"] == "primitive"
    assert captured["disable"] is False


def test_run_process_tree_uses_single_process_pipeline(tmp_path: Path, monkeypatch) -> None:
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

    def fake_process_batch(batch, name_tags_config=None):
        _ = name_tags_config
        captured["batch"] = batch
        return [processed_entry]

    async def fake_save_tree_to_db(
        root_path,
        processed_entries,
        project_name,
        project_description=None,
        created_by=None,
    ):
        _ = (project_description, created_by)
        captured["root_path"] = root_path
        captured["processed_entries"] = processed_entries
        captured["project_name"] = project_name
        return ("project-1", 7)

    monkeypatch.setattr("parsedwg.process_tree.process_batch", fake_process_batch)
    monkeypatch.setattr("parsedwg.process_tree.save_tree_to_db", fake_save_tree_to_db)

    result = process_source(
        source,
        project_name="Sequential Project",
    )

    assert result["project_id"] == "project-1"
    assert result["file_count"] == 1
    assert result["processed_count"] == 1
    assert result["workers"] == 1
    assert result["created_entities"] == 7
    assert result["job_id"] is None
    assert result["mode"] == "direct"
    assert captured["processed_entries"] == [processed_entry]
    assert captured["project_name"] == "Sequential Project"


def test_run_process_tree_dry_mode_skips_db_save(tmp_path: Path, monkeypatch) -> None:
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

    def fake_process_batch(batch, name_tags_config=None):
        _ = (batch, name_tags_config)
        captured["batch"] = batch
        return [processed_entry]

    async def fail_save_tree_to_db(*args, **kwargs):
        _ = (args, kwargs)
        raise AssertionError("save_tree_to_db should not be called in dry mode")

    monkeypatch.setattr("parsedwg.process_tree.process_batch", fake_process_batch)
    monkeypatch.setattr("parsedwg.process_tree.save_tree_to_db", fail_save_tree_to_db)

    result = process_source(
        source,
        project_name="Sequential Project",
        dry_run=True,
    )

    assert result["project_id"] is None
    assert result["file_count"] == 1
    assert result["processed_count"] == 1
    assert result["workers"] == 1
    assert result["created_entities"] == 0
    assert result["dry_run"] is True
    assert result["job_id"] is None
    assert result["mode"] == "direct"