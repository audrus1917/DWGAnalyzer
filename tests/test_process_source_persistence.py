import uuid
from pathlib import Path

from parsedwg.process_source import drawing_to_db
from src.parsedwg.orm import Entity, EntityType


def test_drawing_to_db_sets_file_id_for_all_descendants(tmp_path: Path, monkeypatch) -> None:
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

    class FakeSession:
        def add(self, obj):
            if isinstance(obj, Entity):
                if obj.id is None:
                    obj.id = uuid.uuid4()
                added_entities.append(obj)

        def add_all(self, objects):
            for obj in objects:
                self.add(obj)

        def flush(self):
            return None

        def commit(self):
            return None

    class FakeSessionContext:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_session_factory():
        return FakeSessionContext()

    monkeypatch.setattr("parsedwg.process_source.session_factory", fake_session_factory)

    drawing_to_db(tmp_path, [processed_entry], project_id=100)

    file_entity = next(entity for entity in added_entities if entity.entity_type == EntityType.FILE)
    descendants = [
        entity
        for entity in added_entities
        if entity.entity_type in {EntityType.LAYOUT, EntityType.LAYER, EntityType.BLOCK, EntityType.TEXT}
    ]

    assert descendants
    assert all(entity.file_id == file_entity.id for entity in descendants if entity is not file_entity)


def test_drawing_to_db_commits_primitives_in_batches(tmp_path: Path, monkeypatch) -> None:
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

    class FakeSession:
        def add(self, obj):
            if isinstance(obj, Entity) and obj.id is None:
                obj.id = uuid.uuid4()

        def add_all(self, objects):
            items = list(objects)
            for obj in items:
                self.add(obj)
            if items and all(isinstance(obj, Entity) for obj in items):
                primitive_entity_batch_sizes.append(len(items))

        def flush(self):
            return None

        def commit(self):
            nonlocal commit_calls
            commit_calls += 1

    class FakeSessionContext:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_session_factory():
        return FakeSessionContext()

    monkeypatch.setattr("parsedwg.process_source.session_factory", fake_session_factory)

    drawing_to_db(tmp_path, [processed_entry], project_id=100)

    assert primitive_entity_batch_sizes == [1000, 1]
    assert commit_calls == 2


def test_drawing_to_db_saves_high_detail_payloads(tmp_path: Path, monkeypatch) -> None:
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
            "blocks": [
                {
                    "name": "BLOCK_A",
                    "entity_count": 1,
                    "is_table": False,
                    "description": {
                        "primitives_layers": ["A-TEXT"],
                        "nested_blocks": ["BLOCK_B"],
                        "text_content": ["Подпись"],
                        "attdefs": [{"tag": "ROOM", "default": "101"}],
                        "insert_samples": [{"ROOM": "101"}],
                    },
                }
            ],
            "primitives": [
                {
                    "type": "TEXT",
                    "parent": type("Parent", (), {"name": "BLOCK_A"})(),
                    "layout": "Model",
                    "layer": "A-TEXT",
                    "description": "Подпись",
                    "dxf_attribs": {"insert": [1.0, 2.0, 0.0]},
                    "attribs": {"ROOM": "101"},
                }
            ],
        },
    }

    added_entities: list[Entity] = []

    class FakeSession:
        def add(self, obj):
            if isinstance(obj, Entity):
                if obj.id is None:
                    obj.id = uuid.uuid4()
                added_entities.append(obj)

        def add_all(self, objects):
            for obj in objects:
                self.add(obj)

        def flush(self):
            return None

        def commit(self):
            return None

    class FakeSessionContext:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_session_factory():
        return FakeSessionContext()

    monkeypatch.setattr("parsedwg.process_source.session_factory", fake_session_factory)

    drawing_to_db(tmp_path, [processed_entry], project_id=100, detail_level="high")

    block_entity = next(entity for entity in added_entities if entity.entity_type == EntityType.BLOCK)
    primitive_entity = next(entity for entity in added_entities if entity.entity_type == EntityType.TEXT)

    assert block_entity.data == {
        "entity_count": 1,
        "primitives_layers": ["A-TEXT"],
        "nested_blocks": ["BLOCK_B"],
        "text_content": ["Подпись"],
        "attdefs": [{"tag": "ROOM", "default": "101"}],
        "insert_samples": [{"ROOM": "101"}],
    }
    assert primitive_entity.data == {
        "block": "BLOCK_A",
        "type": "TEXT",
        "text": "Подпись",
        "layer": "A-TEXT",
        "location": [1.0, 2.0, 0.0],
        "layout": "Model",
        "dxf_attribs": {"insert": [1.0, 2.0, 0.0]},
        "attribs": {"ROOM": "101"},
    }


def test_drawing_to_db_prunes_payloads_for_low_detail(tmp_path: Path, monkeypatch) -> None:
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
            "blocks": [
                {
                    "name": "BLOCK_A",
                    "entity_count": 1,
                    "is_table": False,
                    "description": {
                        "primitives_layers": ["A-TEXT"],
                        "nested_blocks": ["BLOCK_B"],
                        "text_content": ["Подпись"],
                    },
                }
            ],
            "primitives": [
                {
                    "type": "TEXT",
                    "parent": type("Parent", (), {"name": "BLOCK_A"})(),
                    "layout": "Model",
                    "layer": "A-TEXT",
                    "description": "Подпись",
                    "dxf_attribs": {"insert": [1.0, 2.0, 0.0]},
                    "attribs": {"ROOM": "101"},
                }
            ],
        },
    }

    added_entities: list[Entity] = []

    class FakeSession:
        def add(self, obj):
            if isinstance(obj, Entity):
                if obj.id is None:
                    obj.id = uuid.uuid4()
                added_entities.append(obj)

        def add_all(self, objects):
            for obj in objects:
                self.add(obj)

        def flush(self):
            return None

        def commit(self):
            return None

    class FakeSessionContext:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_session_factory():
        return FakeSessionContext()

    monkeypatch.setattr("parsedwg.process_source.session_factory", fake_session_factory)

    drawing_to_db(tmp_path, [processed_entry], project_id=100, detail_level="low")

    block_entity = next(entity for entity in added_entities if entity.entity_type == EntityType.BLOCK)
    primitive_entity = next(entity for entity in added_entities if entity.entity_type == EntityType.TEXT)

    assert block_entity.description == ""
    assert block_entity.data == {"entity_count": 1}
    assert primitive_entity.data == {
        "block": "BLOCK_A",
        "type": "TEXT",
        "text": "Подпись",
        "layer": "A-TEXT",
        "location": [1.0, 2.0, 0.0],
    }