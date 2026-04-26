from types import SimpleNamespace
import uuid

from parsedwg.verify_extraction import build_verification_report


def test_build_verification_report_is_ok_for_matching_snapshot() -> None:
    file_id = uuid.uuid4()
    layout_id = uuid.uuid4()
    layer_id = uuid.uuid4()
    block_id = uuid.uuid4()
    text_id = uuid.uuid4()
    insert_id = uuid.uuid4()

    report = build_verification_report(
        source_summary={
            "layouts": [{"name": "Model"}],
            "layers": [{"name": "A-TEXT", "data": {}}],
            "blocks": [{"name": "BLOCK_A", "entity_count": 2}],
            "primitives": [
                {"block": "BLOCK_A", "type": "TEXT", "layout": "Model", "layer": "A-TEXT"},
                {
                    "block": "BLOCK_A",
                    "type": "INSERT",
                    "layout": "Model",
                    "layer": "A-TEXT",
                    "target_block": "BLOCK_A",
                },
            ],
        },
        db_snapshot={
            "file_entity": SimpleNamespace(id=file_id),
            "layouts": [SimpleNamespace(id=layout_id, name="Model", file_id=file_id)],
            "layers": [
                SimpleNamespace(id=layer_id, name="A-TEXT", parent_id=file_id, file_id=file_id)
            ],
            "blocks": [
                SimpleNamespace(
                    id=block_id,
                    name="BLOCK_A",
                    data={"entity_count": 2},
                    file_id=file_id,
                )
            ],
            "primitives": [
                SimpleNamespace(
                    id=text_id,
                    name="TEXT",
                    entity_type="TEXT",
                    data={"block": "BLOCK_A", "layout": "Model", "layer": "A-TEXT"},
                    file_id=file_id,
                ),
                SimpleNamespace(
                    id=insert_id,
                    name="INSERT",
                    entity_type="INSERT",
                    data={
                        "block": "BLOCK_A",
                        "layout": "Model",
                        "layer": "A-TEXT",
                        "target_block": "BLOCK_A",
                    },
                    file_id=file_id,
                ),
            ],
            "on_layer_links": {(text_id, layer_id), (insert_id, layer_id)},
        },
    )

    assert report["ok"] is True
    assert report["blocks"]["mismatches"] == []
    assert report["primitive_counts"]["mismatches"] == []
    assert report["insert_targets"]["unresolved"] == []
    assert report["layer_links"]["missing"] == []
    assert report["file_id_check"]["invalid"] == []


def test_build_verification_report_detects_mismatches() -> None:
    file_id = uuid.uuid4()
    layout_id = uuid.uuid4()
    block_id = uuid.uuid4()
    primitive_id = uuid.uuid4()

    report = build_verification_report(
        source_summary={
            "layouts": [{"name": "Model"}],
            "layers": [{"name": "A-TEXT", "data": {}}],
            "blocks": [{"name": "BLOCK_A", "entity_count": 2}],
            "primitives": [
                {"block": "BLOCK_A", "type": "TEXT", "layout": "Model", "layer": "A-TEXT"},
            ],
        },
        db_snapshot={
            "file_entity": SimpleNamespace(id=file_id),
            "layouts": [SimpleNamespace(id=layout_id, name="Model", file_id=file_id)],
            "layers": [],
            "blocks": [
                SimpleNamespace(
                    id=block_id,
                    name="BLOCK_A",
                    data={"entity_count": 1},
                    file_id=file_id,
                )
            ],
            "primitives": [
                SimpleNamespace(
                    id=primitive_id,
                    name="INSERT",
                    entity_type="INSERT",
                    data={"block": "BLOCK_A", "layout": "Model", "layer": "A-TEXT", "target_block": "MISSING"},
                    file_id=None,
                ),
            ],
            "on_layer_links": set(),
        },
    )

    assert report["ok"] is False
    assert report["layouts"]["mismatches"]
    assert report["blocks"]["mismatches"]
    assert report["primitive_counts"]["mismatches"]
    assert report["insert_targets"]["unresolved"] == ["MISSING"]
    assert report["layer_links"]["missing"]
    assert report["file_id_check"]["invalid"]