import json

from parsedwg.cli import main


def test_main_interpret_entities_dry_mode(monkeypatch, capsys) -> None:
    async def fake_list_entities(
        entity_ids: list[str] | None = None,
        entity_type: str | None = None,
        file_id: str | None = None,
    ):
        assert entity_ids is None
        assert entity_type == "BLOCK"
        assert file_id is None
        return [
            {"id": "aaa-001", "name": "Насос-пожарный", "description": "", "entity_type": "BLOCK"},
            {"id": "aaa-002", "name": "Клапан-ДУ", "description": "", "entity_type": "BLOCK"},
        ]

    def stub_call(*_args, **_kwargs):
        return "1. Инженерное оборудование."

    async def fake_save(_entity_id: str, _text: str) -> None:
        raise AssertionError("В dry-режиме сохранение не должно вызываться")

    monkeypatch.setattr(
        "parsedwg.db.list_entities_for_semantic_categorization", fake_list_entities
    )
    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.call_ollama_name_meaning",
        stub_call,
    )
    monkeypatch.setattr("parsedwg.db.save_short_interpretation", fake_save)

    exit_code = main(["interpret-entities", "--entity-type", "BLOCK", "--dry"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == [
        {
            "entity_id": "aaa-001",
            "entity_name": "Насос-пожарный",
            "text": "1. Инженерное оборудование.",
            "status": "ok",
        },
        {
            "entity_id": "aaa-002",
            "entity_name": "Клапан-ДУ",
            "text": "1. Инженерное оборудование.",
            "status": "ok",
        },
    ]


def test_main_interpret_blocks_dry_mode(monkeypatch, capsys) -> None:
    descriptions = {
        "Насос-ДУ": {"name": "Насос-ДУ", "layers": [{"name": "M-NASOS"}]},
        "Клапан-ДУ": {"name": "Клапан-ДУ", "layers": [{"name": "M-KLAPAN"}]},
    }

    async def fake_list_blocks_for_interpretation(
        block_ids: list[str] | None = None,
        file_id: str | None = None,
    ):
        assert block_ids is None
        assert file_id == "file-001"
        return [
            {"id": "blk-001", "name": "Насос-ДУ", "description": "", "file_id": "file-001"},
            {"id": "blk-002", "name": "Клапан-ДУ", "description": "", "file_id": "file-001"},
        ]

    async def fake_get_full_description(block_name: str, file_id: str | None = None):
        assert file_id == "file-001"
        return descriptions[block_name]

    def stub_call(*_args, **kwargs):
        extra_context = kwargs.get("extra_context", "")
        if "максимально подробное описание" in extra_context:
            return f"FULL::{kwargs['name']}"
        return f"SHORT::{kwargs['name']}"

    monkeypatch.setattr(
        "parsedwg.db.list_blocks_for_interpretation",
        fake_list_blocks_for_interpretation,
    )
    monkeypatch.setattr("parsedwg.db.get_full_description", fake_get_full_description)
    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.call_ollama_name_meaning",
        stub_call,
    )

    exit_code = main(["interpret-blocks", "file-001", "--dry"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    first_text = json.dumps(descriptions["Насос-ДУ"], ensure_ascii=False, sort_keys=True)
    second_text = json.dumps(descriptions["Клапан-ДУ"], ensure_ascii=False, sort_keys=True)
    assert payload == [
        {
            "status": "ok",
            "block_id": "blk-001",
            "block_name": "Насос-ДУ",
            "duration_seconds": payload[0]["duration_seconds"],
            "short_interpretation": f"SHORT::{first_text}",
            "description": first_text,
            "full_interpretation": f"FULL::{first_text}",
        },
        {
            "status": "ok",
            "block_id": "blk-002",
            "block_name": "Клапан-ДУ",
            "duration_seconds": payload[1]["duration_seconds"],
            "short_interpretation": f"SHORT::{second_text}",
            "description": second_text,
            "full_interpretation": f"FULL::{second_text}",
        },
    ]


def test_main_interpret_block_dispatches_single_entity_id(monkeypatch) -> None:
    captured_args: dict[str, object] = {}

    def fake_handle_interpret_blocks_command(
        block_ids: list[str] | None,
        file_ref: str | None,
        by_path: bool,
        extra_context: str,
        ai_model: str,
        ai_base_url: str,
        ai_api_key: str,
        workers: int,
        dry: bool,
    ) -> int:
        captured_args.update(
            {
                "block_ids": block_ids,
                "file_ref": file_ref,
                "by_path": by_path,
                "extra_context": extra_context,
                "workers": workers,
                "dry": dry,
            }
        )
        _ = (ai_model, ai_base_url, ai_api_key)
        return 0

    monkeypatch.setattr(
        "parsedwg.cli.handle_interpret_blocks_command",
        fake_handle_interpret_blocks_command,
    )

    exit_code = main([
        "interpret-block",
        "--entity-id",
        "blk-entity-001",
        "--extra-context",
        "раздел ВК",
        "--dry",
    ])

    assert exit_code == 0
    assert captured_args == {
        "block_ids": ["blk-entity-001"],
        "file_ref": None,
        "by_path": False,
        "extra_context": "раздел ВК",
        "workers": 1,
        "dry": True,
    }


def test_main_verify_extraction_dispatches_handler(tmp_path, monkeypatch) -> None:
    source_path = tmp_path / "sample.dxf"
    source_path.write_text("stub", encoding="utf-8")
    captured_args: dict[str, object] = {}

    def fake_handle_verify_extraction_command(drawing_path, file_id=None) -> int:
        captured_args["drawing_path"] = drawing_path
        captured_args["file_id"] = file_id
        return 0

    monkeypatch.setattr(
        "parsedwg.cli.handle_verify_extraction_command",
        fake_handle_verify_extraction_command,
    )

    exit_code = main([
        "verify-extraction",
        str(source_path),
        "--file-id",
        "11111111-1111-1111-1111-111111111111",
    ])

    assert exit_code == 0
    assert captured_args == {
        "drawing_path": source_path,
        "file_id": "11111111-1111-1111-1111-111111111111",
    }