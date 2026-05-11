import json
from pathlib import Path

from parsedwg.cli import main


def test_main_process_runs_pipeline(tmp_path, monkeypatch, capsys) -> None:
    source_dir = tmp_path / "tower_A"
    source_dir.mkdir(parents=True)

    captured_args: dict[str, object] = {}

    def fake_run(
        source_path: Path,
        name_tags_config: dict[str, str] | None = None,
        **kwargs,
    ) -> dict[str, object]:
        project_name = kwargs.get("project_name")
        project_description = kwargs.get("project_description")
        created_by = kwargs.get("created_by")
        captured_args["source_path"] = source_path
        captured_args["project_name"] = project_name
        captured_args["project_description"] = project_description
        captured_args["created_by"] = created_by
        captured_args["name_tags_config"] = name_tags_config
        return {
            "project_id": "11111111-1111-1111-1111-111111111111",
            "file_count": 3,
            "processed_count": 3,
            "mode": "direct",
            "created_entities": 42,
        }

    monkeypatch.setattr("parsedwg.cli.run_process_tree", fake_run)

    exit_code = main(
        [
            "process",
            str(source_dir),
            "--project-name",
            "Башня А",
            "--project-description",
            "Тестовый проект",
            "--created-by",
            "andrus",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_args["source_path"] == source_dir
    assert captured_args["project_name"] == "Башня А"
    assert captured_args["project_description"] == "Тестовый проект"
    assert captured_args["created_by"] == "andrus"
    assert captured_args["name_tags_config"] is None
    assert "Найдено файлов: 3" in captured.out
    assert "Обработано файлов: 3" in captured.out
    assert "Режим обработки: direct" in captured.out
    assert "Создано сущностей в БД: 42" in captured.out


def test_main_process_passes_ai_name_tags_config(tmp_path, monkeypatch) -> None:
    source_dir = tmp_path / "tower_A"
    source_dir.mkdir(parents=True)

    captured_args: dict[str, object] = {}

    def fake_config_builder(enabled: bool, model: str, base_url: str, api_key: str):
        captured_args["enabled"] = enabled
        captured_args["model"] = model
        captured_args["base_url"] = base_url
        captured_args["api_key"] = api_key
        return {
            "model": model,
            "base_url": base_url,
            "api_key": api_key,
        }

    def fake_run(
        source_path: Path,
        name_tags_config: dict[str, str] | None = None,
        **kwargs,
    ) -> dict[str, object]:
        _ = kwargs
        captured_args["source_path"] = source_path
        captured_args["name_tags_config"] = name_tags_config
        return {
            "project_id": "11111111-1111-1111-1111-111111111111",
            "file_count": 1,
            "processed_count": 1,
            "mode": "direct",
            "created_entities": 10,
        }

    monkeypatch.setattr("parsedwg.cli.get_name_tags_config", fake_config_builder)
    monkeypatch.setattr("parsedwg.cli.run_process_tree", fake_run)

    exit_code = main(
        [
            "process",
            str(source_dir),
            "--ai-name-tags",
            "--ai-model",
            "llama3.1:70b",
            "--ai-base-url",
            "http://localhost:11434/v1",
            "--ai-api-key",
            "secret",
        ]
    )

    assert exit_code == 0
    assert captured_args["enabled"] is True
    assert captured_args["model"] == "llama3.1:70b"
    assert captured_args["base_url"] == "http://localhost:11434/v1"
    assert captured_args["api_key"] == "secret"
    assert captured_args["source_path"] == source_dir
    assert captured_args["name_tags_config"] == {
        "model": "llama3.1:70b",
        "base_url": "http://localhost:11434/v1",
        "api_key": "secret",
    }


def test_main_process_without_optional_flags_runs_pipeline(tmp_path, monkeypatch) -> None:
    source_dir = tmp_path / "tower_A"
    source_dir.mkdir(parents=True)

    captured_args: dict[str, object] = {}

    def fake_run(
        source_path: Path,
        name_tags_config: dict[str, str] | None = None,
        **kwargs,
    ) -> dict[str, object]:
        _ = kwargs
        captured_args["source_path"] = source_path
        captured_args["name_tags_config"] = name_tags_config
        return {
            "project_id": "11111111-1111-1111-1111-111111111111",
            "file_count": 1,
            "processed_count": 1,
            "mode": "direct",
            "created_entities": 1,
        }

    monkeypatch.setattr("parsedwg.cli.run_process_tree", fake_run)

    exit_code = main(["process", str(source_dir)])

    assert exit_code == 0
    assert captured_args["source_path"] == source_dir
    assert captured_args["name_tags_config"] is None


def test_main_process_passes_dry_flag_and_prints_dry_message(tmp_path, monkeypatch, capsys) -> None:
    source_dir = tmp_path / "tower_A"
    source_dir.mkdir(parents=True)

    captured_args: dict[str, object] = {}

    def fake_run(
        source_path: Path,
        name_tags_config: dict[str, str] | None = None,
        dry_run: bool = False,
        **kwargs,
    ) -> dict[str, object]:
        _ = (kwargs, name_tags_config)
        captured_args["source_path"] = source_path
        captured_args["dry_run"] = dry_run
        return {
            "project_id": None,
            "file_count": 2,
            "processed_count": 2,
            "mode": "direct",
            "dry_run": True,
            "created_entities": 0,
        }

    monkeypatch.setattr("parsedwg.cli.run_process_tree", fake_run)

    exit_code = main(["process", str(source_dir), "--dry"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_args["source_path"] == source_dir
    assert captured_args["dry_run"] is True
    assert "Dry run: запись в БД отключена" in captured.out
    assert "Создано сущностей в БД: 0" in captured.out


def test_main_export_block_png_runs_pipeline(tmp_path, monkeypatch, capsys) -> None:
    source_path = tmp_path / "sample.dxf"
    source_path.write_text("stub", encoding="utf-8")
    target_path = tmp_path / "block.png"

    captured_args: dict[str, object] = {}

    class StubExplorer:
        def __init__(self, drawing: Path):
            captured_args["drawing"] = drawing

        def export_block_png(
            self,
            block_name: str,
            output_path: Path | None = None,
            dpi: int = 300,
        ) -> Path:
            captured_args["block_name"] = block_name
            captured_args["output_path"] = output_path
            captured_args["dpi"] = dpi
            return output_path or target_path

    monkeypatch.setattr("parsedwg.cli.DXFExplorer", StubExplorer)

    exit_code = main(
        [
            "export-block-png",
            str(source_path),
            "BLOCK_A",
            "-o",
            str(target_path),
            "--dpi",
            "200",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_args["drawing"] == source_path
    assert captured_args["block_name"] == "BLOCK_A"
    assert captured_args["output_path"] == target_path
    assert captured_args["dpi"] == 200
    assert f"PNG сохранён: {target_path}" in captured.out


def test_main_export_block_svg_runs_pipeline(tmp_path, monkeypatch, capsys) -> None:
    source_path = tmp_path / "sample.dxf"
    source_path.write_text("stub", encoding="utf-8")
    target_path = tmp_path / "block.svg"

    captured_args: dict[str, object] = {}

    class StubExplorer:
        def __init__(self, drawing: Path):
            captured_args["drawing"] = drawing

        def export_block_svg(
            self,
            block_name: str,
            output_path: Path | None = None,
        ) -> Path:
            captured_args["block_name"] = block_name
            captured_args["output_path"] = output_path
            return output_path or target_path

    monkeypatch.setattr("parsedwg.cli.DXFExplorer", StubExplorer)

    exit_code = main(
        [
            "export-block-svg",
            str(source_path),
            "BLOCK_A",
            "-o",
            str(target_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_args["drawing"] == source_path
    assert captured_args["block_name"] == "BLOCK_A"
    assert captured_args["output_path"] == target_path
    assert f"SVG сохранён: {target_path}" in captured.out


def test_main_export_block_dxf_prints_text(tmp_path, monkeypatch, capsys) -> None:
    source_path = tmp_path / "sample.dxf"
    source_path.write_text("stub", encoding="utf-8")
    captured_args: dict[str, object] = {}
    dxf_text = "  0\nBLOCK\n  2\nBLOCK_A\n  0\nENDBLK\n"

    class StubExplorer:
        def __init__(self, drawing: Path):
            captured_args["drawing"] = drawing

        def export_block_dxf(self, block_name: str) -> str:
            captured_args["block_name"] = block_name
            return dxf_text

    monkeypatch.setattr("parsedwg.cli.DXFExplorer", StubExplorer)

    exit_code = main(["export-block-dxf", str(source_path), "BLOCK_A"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_args["drawing"] == source_path
    assert captured_args["block_name"] == "BLOCK_A"
    assert captured.out == f"{dxf_text}\n"


def test_main_describe_block_outputs_json(tmp_path, monkeypatch, capsys) -> None:
    source_path = tmp_path / "sample.dxf"
    source_path.write_text("stub", encoding="utf-8")
    payload = {
        "drawing": str(source_path),
        "block": "BLOCK_A",
        "description": "Сущностей: 2. Вставок: 1",
        "entity_count": 2,
        "is_table": False,
        "entities": [{"type": "LINE"}],
        "inserts": [{"container_type": "layout", "container_name": "Model"}],
        "insert_count": 1,
    }
    captured_args: dict[str, object] = {}

    class StubExplorer:
        def __init__(self, drawing: Path):
            captured_args["drawing"] = drawing

        def describe_block(self, block_name: str) -> dict[str, object]:
            captured_args["block_name"] = block_name
            return payload

    monkeypatch.setattr("parsedwg.cli.DXFExplorer", StubExplorer)

    exit_code = main(["describe-block", str(source_path), "BLOCK_A"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_args["drawing"] == source_path
    assert captured_args["block_name"] == "BLOCK_A"
    assert json.loads(captured.out) == payload


def test_main_describe_block_writes_json_file(tmp_path, monkeypatch, capsys) -> None:
    source_path = tmp_path / "sample.dxf"
    source_path.write_text("stub", encoding="utf-8")
    output_path = tmp_path / "block.json"
    payload = {
        "drawing": str(source_path),
        "block": "BLOCK_A",
        "description": "Сущностей: 1. Вставок: 0",
        "entity_count": 1,
        "is_table": False,
        "entities": [{"type": "TEXT", "text": "A"}],
        "inserts": [],
        "insert_count": 0,
    }

    class StubExplorer:
        def __init__(self, drawing: Path):
            assert drawing == source_path

        def describe_block(self, block_name: str) -> dict[str, object]:
            assert block_name == "BLOCK_A"
            return payload

    monkeypatch.setattr("parsedwg.cli.DXFExplorer", StubExplorer)

    exit_code = main(["describe-block", str(source_path), "BLOCK_A", "-o", str(output_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8")) == payload
    assert captured.out == ""


def test_main_extract_name_tags_writes_json(tmp_path) -> None:
    source_dir = tmp_path / "names"
    source_dir.mkdir(parents=True)
    file_path = source_dir / "Этаж_3_кровля.dxf"
    file_path.write_text("stub", encoding="utf-8")

    output_path = tmp_path / "tags.json"
    exit_code = main(["extract-name-tags", str(source_dir), "-o", str(output_path)])

    assert exit_code == 0
    rows = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(rows) == 1
    assert rows[0]["name"] == "Этаж_3_кровля.dxf"
    assert "этаж:3" in rows[0]["tags"]
    assert "кровля" in rows[0]["tags"]


def test_main_extract_name_tags_handles_ai_runtime_error(tmp_path, monkeypatch) -> None:
    source_dir = tmp_path / "names"
    source_dir.mkdir(parents=True)
    (source_dir / "Этаж_3_кровля.dxf").write_text("stub", encoding="utf-8")

    class FailingExtractor:
        def extract(self, _text: str) -> list[str]:
            raise RuntimeError("model not found")

    monkeypatch.setattr(
        "parsedwg.cli.get_name_tags_config",
        lambda enabled, model, base_url, api_key: {
            "model": model,
            "base_url": base_url,
            "api_key": api_key,
        },
    )
    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.LangChainNameTagsExtractor.from_config",
        lambda _cfg: FailingExtractor(),
    )

    exit_code = main(["extract-name-tags", str(source_dir), "--ai-name-tags"])

    assert exit_code == 1


def test_main_extract_token_tags_prints_csv(tmp_path, monkeypatch, capsys) -> None:
    _ = tmp_path

    class StubExtractor:
        def extract_token_meanings_json(self, tokens: list[str], extra_context: str = "") -> str:
            assert tokens == ["M_Doors", "M_Wall_Glass"]
            assert extra_context == "строительство, чертеж"
            return '{"M_Doors": ["двери"], "M_Wall_Glass": ["стекло", "перегородки"]}'

    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.LangChainNameTagsExtractor.from_config",
        lambda _cfg: StubExtractor(),
    )

    exit_code = main(["extract-token-tags", "M_Doors", "M_Wall_Glass"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {
        "M_Doors": ["двери"],
        "M_Wall_Glass": ["стекло", "перегородки"],
    }


def test_main_extract_token_tags_handles_ai_runtime_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.LangChainNameTagsExtractor.from_config",
        lambda _cfg: (_ for _ in ()).throw(RuntimeError("model not found")),
    )

    exit_code = main(["extract-token-tags", "M_Doors"])

    assert exit_code == 1


def test_main_extract_token_tags_reads_layer_names_from_drawing(tmp_path, monkeypatch, capsys) -> None:
    source_path = tmp_path / "layers.dxf"

    from ezdxf.filemanagement import new

    doc = new()
    doc.layers.add("M_Doors")
    doc.layers.add("M_Wall_Glass")
    doc.saveas(source_path)

    class StubExtractor:
        def extract_token_meanings_json(self, tokens: list[str], extra_context: str = "") -> str:
            assert "M_Doors" in tokens
            assert "M_Wall_Glass" in tokens
            assert extra_context == "строительство, чертеж"
            return '{"M_Doors": ["двери"], "M_Wall_Glass": ["стекло", "перегородки"]}'

    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.LangChainNameTagsExtractor.from_config",
        lambda _cfg: StubExtractor(),
    )

    exit_code = main(["extract-token-tags", "--drawing", str(source_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {
        "M_Doors": ["двери"],
        "M_Wall_Glass": ["стекло", "перегородки"],
    }


def test_main_extract_token_tags_with_scores_prints_weighted_json(monkeypatch, capsys) -> None:
    class StubExtractor:
        def extract_token_meanings_scored_json(
            self,
            tokens: list[str],
            extra_context: str = "",
        ) -> str:
            assert tokens == ["M_Doors"]
            assert extra_context == "строительство, чертеж"
            return (
                '{"M_Doors": ['
                '{"meaning": "дверь", "score": 0.96}, '
                '{"meaning": "проем", "score": 0.41}]}'
            )

    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.LangChainNameTagsExtractor.from_config",
        lambda _cfg: StubExtractor(),
    )

    exit_code = main(["extract-token-tags", "M_Doors", "--with-scores"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {
        "M_Doors": [
            {"meaning": "дверь", "score": 0.96},
            {"meaning": "проем", "score": 0.41},
        ]
    }


def test_main_extract_name_meaning_prints_freeform_text(monkeypatch, capsys) -> None:
    def stub_call(name, chat_url, model, extra_context="", **kwargs):
        assert name == "Насос пожаротушения"
        assert extra_context == "секция А, пожаротушение"
        assert chat_url.endswith("/api/chat")
        assert model == "llama3.1:8b"
        return "1. Насос — оборудование системы пожаротушения.\n2. Числовые идентификаторы отсутствуют."

    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.call_ollama_name_meaning",
        stub_call,
    )

    exit_code = main([
        "extract-name-meaning",
        "Насос пожаротушения",
        "--extra-context",
        "секция А, пожаротушение",
    ])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Насос" in captured.out
    assert "пожаротушения" in captured.out


def test_main_extract_name_meaning_includes_floor_and_elevation(monkeypatch, capsys) -> None:
    def stub_call(name, chat_url, model, extra_context="", **kwargs):
        assert name == "План 4й этаж отметка +2метра"
        assert chat_url.endswith("/api/chat")
        return "1. Архитектурный план.\n2. 4-й этаж; отметка +2 м."

    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.call_ollama_name_meaning",
        stub_call,
    )

    exit_code = main(["extract-name-meaning", "План 4й этаж отметка +2метра"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "4-й этаж" in captured.out
    assert "+2 м" in captured.out


def test_main_extract_name_meaning_handles_ai_runtime_error(monkeypatch) -> None:
    def stub_call(name, chat_url, model, extra_context="", **kwargs):
        _ = (name, chat_url, model, extra_context, kwargs)
        raise RuntimeError("model not found")

    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.call_ollama_name_meaning",
        stub_call,
    )

    exit_code = main(["extract-name-meaning", "Насос пожаротушения"])

    assert exit_code == 1


def test_main_extract_name_meaning_loads_name_from_db_by_entity_id(monkeypatch, capsys) -> None:
    async def fake_get_entity_name_by_id(entity_id: str) -> str | None:
        assert entity_id == "11111111-1111-1111-1111-111111111111"
        return "Клапан дымоудаления"

    def stub_call(name, chat_url, model, extra_context="", **kwargs):
        assert name == "Клапан дымоудаления"
        assert extra_context == "раздел ДУ"
        assert chat_url.endswith("/api/chat")
        return "1. Клапан системы дымоудаления."

    monkeypatch.setattr("parsedwg.db.get_entity_name_by_id", fake_get_entity_name_by_id)
    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.call_ollama_name_meaning",
        stub_call,
    )

    exit_code = main([
        "extract-name-meaning",
        "--entity-id",
        "11111111-1111-1111-1111-111111111111",
        "--extra-context",
        "раздел ДУ",
    ])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Клапан дымоудаления" in captured.out
    assert "Клапан системы дымоудаления" in captured.out


def test_main_extract_name_meaning_returns_not_found_for_missing_entity_id(monkeypatch, capsys) -> None:
    async def fake_get_entity_name_by_id(_entity_id: str) -> str | None:
        return None

    monkeypatch.setattr("parsedwg.db.get_entity_name_by_id", fake_get_entity_name_by_id)

    exit_code = main([
        "extract-name-meaning",
        "--entity-id",
        "22222222-2222-2222-2222-222222222222",
    ])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Сущность не найдена" in captured.out


def test_main_extract_name_meaning_requires_exactly_one_input() -> None:
    exit_code = main(["extract-name-meaning"])
    assert exit_code == 3

    exit_code = main([
        "extract-name-meaning",
        "Насос",
        "--entity-id",
        "33333333-3333-3333-3333-333333333333",
    ])
    assert exit_code == 3


def test_derive_ollama_chat_url_strips_v1_suffix() -> None:
    from parsedwg.cli import _derive_ollama_chat_url

    assert _derive_ollama_chat_url("http://localhost:11434/v1") == "http://localhost:11434/api/chat"
    assert _derive_ollama_chat_url("http://localhost:11434") == "http://localhost:11434/api/chat"
    assert _derive_ollama_chat_url("http://localhost:11434/v1/") == "http://localhost:11434/api/chat"


def test_main_explain_block_fetches_name_and_calls_llm(monkeypatch, capsys) -> None:
    async def fake_get_entity_name_by_id(entity_id: str) -> str | None:
        assert entity_id == "11111111-1111-1111-1111-111111111111"
        return "Насос-пожарный-4этаж"

    def stub_call(name, chat_url, model, extra_context="", **_kwargs):
        assert name == "Насос-пожарный-4этаж"
        assert extra_context == "раздел ВК"
        assert chat_url.endswith("/api/chat")
        return "1. Пожарный насос.\n2. 4-й этаж."

    monkeypatch.setattr("parsedwg.db.get_entity_name_by_id", fake_get_entity_name_by_id)
    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.call_ollama_name_meaning",
        stub_call,
    )

    exit_code = main([
        "explain-block",
        "11111111-1111-1111-1111-111111111111",
        "--extra-context", "раздел ВК",
    ])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Насос-пожарный-4этаж" in captured.out
    assert "Пожарный насос" in captured.out
    assert "4-й этаж" in captured.out


def test_main_explain_block_returns_not_found_when_missing(monkeypatch, capsys) -> None:
    async def fake_get_entity_name_by_id(entity_id: str) -> str | None:
        return None

    monkeypatch.setattr("parsedwg.db.get_entity_name_by_id", fake_get_entity_name_by_id)

    exit_code = main(["explain-block", "22222222-2222-2222-2222-222222222222"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "не найден" in captured.out


def test_main_explain_block_propagates_llm_error(monkeypatch) -> None:
    async def fake_get_entity_name_by_id(_entity_id: str) -> str | None:
        return "Клапан-дымоудаления"

    def stub_call(*_args, **_kwargs):
        raise RuntimeError("timeout")

    monkeypatch.setattr("parsedwg.db.get_entity_name_by_id", fake_get_entity_name_by_id)
    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.call_ollama_name_meaning",
        stub_call,
    )

    exit_code = main(["explain-block", "33333333-3333-3333-3333-333333333333"])

    assert exit_code == 1


def test_main_interpret_entities_dry_mode(monkeypatch, capsys) -> None:
    saved_ids: list[str] = []

    async def fake_list_entities(
        entity_ids: list[str] | None = None, entity_type: str | None = None
    ):
        assert entity_type == "BLOCK"
        return [
            {"id": "aaa-001", "name": "Насос-пожарный", "description": "", "entity_type": "BLOCK"},
            {"id": "aaa-002", "name": "Клапан-ДУ", "description": "", "entity_type": "BLOCK"},
        ]

    def stub_call(*_args, **_kwargs):
        return "1. Инженерное оборудование."

    async def fake_save(entity_id: str, text: str) -> None:
        saved_ids.append(entity_id)

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
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload == [
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
    assert not saved_ids  # --dry: ничего не сохраняется


def test_main_interpret_entities_saves_to_db(monkeypatch) -> None:
    saved: dict[str, str] = {}

    async def fake_list_entities(
        entity_ids: list[str] | None = None, entity_type: str | None = None
    ):
        return [
            {"id": "bbb-001", "name": "Вентилятор-ДУ-1", "description": "", "entity_type": "BLOCK"}
        ]

    def stub_call(*_args, **_kwargs):
        return "1. Вентилятор дымоудаления.\n2. Первый."

    async def fake_save(entity_id: str, text: str) -> None:
        saved[entity_id] = text

    monkeypatch.setattr(
        "parsedwg.db.list_entities_for_semantic_categorization", fake_list_entities
    )
    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.call_ollama_name_meaning",
        stub_call,
    )
    monkeypatch.setattr("parsedwg.db.save_short_interpretation", fake_save)

    exit_code = main(["interpret-entities", "--entity-type", "BLOCK"])

    assert exit_code == 0
    assert saved == {"bbb-001": "1. Вентилятор дымоудаления.\n2. Первый."}


def test_main_interpret_entities_no_entities(monkeypatch, capsys) -> None:
    async def fake_list_entities(
        entity_ids: list[str] | None = None, entity_type: str | None = None
    ):
        return []

    monkeypatch.setattr(
        "parsedwg.db.list_entities_for_semantic_categorization", fake_list_entities
    )

    exit_code = main(["interpret-entities", "--entity-type", "UNKNOWN"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Нет сущностей" in captured.out


def test_main_interpret_entities_continues_after_entity_error(monkeypatch, capsys) -> None:
    saved: dict[str, str] = {}

    async def fake_list_entities(
        entity_ids: list[str] | None = None, entity_type: str | None = None
    ):
        return [
            {"id": "ccc-001", "name": "Вентилятор-ДУ-1", "description": "", "entity_type": "BLOCK"},
            {"id": "ccc-002", "name": "Клапан-ДУ-2", "description": "", "entity_type": "BLOCK"},
        ]

    def stub_call(*_args, **kwargs):
        if kwargs.get("name") == "Клапан-ДУ-2":
            raise RuntimeError("timeout")
        return "1. Оборудование дымоудаления."

    async def fake_save(entity_id: str, text: str) -> None:
        saved[entity_id] = text

    monkeypatch.setattr(
        "parsedwg.db.list_entities_for_semantic_categorization", fake_list_entities
    )
    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.call_ollama_name_meaning",
        stub_call,
    )
    monkeypatch.setattr("parsedwg.db.save_short_interpretation", fake_save)

    exit_code = main(["interpret-entities", "--entity-type", "BLOCK", "--workers", "2"])

    assert exit_code == 0
    assert saved == {"ccc-001": "1. Оборудование дымоудаления."}
    captured = capsys.readouterr()
    assert "Интерпретировано: 1" in captured.out
    assert "Ошибок: 1" in captured.out


def test_main_interpret_entities_dry_mode_shows_entity_errors(monkeypatch, capsys) -> None:
    async def fake_list_entities(
        entity_ids: list[str] | None = None, entity_type: str | None = None
    ):
        return [
            {"id": "ddd-001", "name": "Насос-1", "description": "", "entity_type": "BLOCK"},
            {"id": "ddd-002", "name": "Клапан-2", "description": "", "entity_type": "BLOCK"},
        ]

    def stub_call(*_args, **kwargs):
        if kwargs.get("name") == "Клапан-2":
            raise RuntimeError("timeout")
        return "1. Насосное оборудование."

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

    exit_code = main(["interpret-entities", "--entity-type", "BLOCK", "--workers", "2", "--dry"])

    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert any(
        item == {
            "entity_id": "ddd-001",
            "entity_name": "Насос-1",
            "text": "1. Насосное оборудование.",
            "status": "ok",
        }
        for item in payload
    )
    assert any(
        item == {
            "status": "error",
            "entity_id": "ddd-002",
            "entity_name": "Клапан-2",
            "error": "timeout",
        }
        for item in payload
    )


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
    monkeypatch.setattr(
        "parsedwg.db.get_full_description",
        fake_get_full_description,
    )
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
    assert all(isinstance(item["duration_seconds"], (int, float)) for item in payload)


def test_main_interpret_blocks_saves_both_interpretations(monkeypatch, capsys) -> None:
    saved: dict[str, dict[str, str]] = {}
    saved_descriptions: dict[str, str] = {}
    full_description_payload = {
        "name": "Вентилятор-ДУ-1",
        "layers": [{"name": "M-VENT", "short_interpretation": "вентиляция"}],
    }

    async def fake_list_blocks_for_interpretation(
        block_ids: list[str] | None = None,
        file_id: str | None = None,
    ):
        assert block_ids == ["11111111-1111-1111-1111-111111111111"]
        assert file_id is None
        return [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "name": "Вентилятор-ДУ-1",
                "description": "",
                "file_id": "",
            }
        ]

    async def fake_get_full_description(block_name: str, file_id: str | None = None):
        assert block_name == "Вентилятор-ДУ-1"
        assert file_id is None
        return full_description_payload

    async def fake_save_block_description(block_id: str, description: str) -> None:
        saved_descriptions[block_id] = description

    async def fake_save_block_interpretations(
        block_id: str,
        short_interpretation: str,
        full_interpretation: str,
        description: str,
    ) -> None:
        saved[block_id] = {
            "description": description,
            "short": short_interpretation,
            "full": full_interpretation,
        }

    monkeypatch.setattr(
        "parsedwg.db.list_blocks_for_interpretation",
        fake_list_blocks_for_interpretation,
    )
    monkeypatch.setattr(
        "parsedwg.db.get_full_description",
        fake_get_full_description,
    )
    monkeypatch.setattr(
        "parsedwg.db.save_block_description",
        fake_save_block_description,
    )
    monkeypatch.setattr(
        "parsedwg.db.save_block_interpretations",
        fake_save_block_interpretations,
    )
    full_description_text = json.dumps(full_description_payload, ensure_ascii=False, sort_keys=True)
    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.call_ollama_name_meaning",
        lambda *_args, **kwargs: (
            f"FULL::{kwargs['name']}"
            if "максимально подробное описание" in kwargs.get("extra_context", "")
            else f"SHORT::{kwargs['name']}"
        ),
    )

    exit_code = main([
        "interpret-blocks",
        "--block-id",
        "11111111-1111-1111-1111-111111111111",
    ])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert saved_descriptions == {
        "11111111-1111-1111-1111-111111111111": full_description_text,
    }
    assert saved == {
        "11111111-1111-1111-1111-111111111111": {
            "description": full_description_text,
            "short": f"SHORT::{full_description_text}",
            "full": f"FULL::{full_description_text}",
        }
    }
    assert "обработан за" in captured.out
    assert "Интерпретировано блоков: 1" in captured.out


def test_main_interpret_blocks_reports_failures(monkeypatch, capsys) -> None:
    descriptions = {
        "Насос-1": {"name": "Насос-1", "layers": []},
        "Клапан-2": {"name": "Клапан-2", "layers": []},
    }

    async def fake_list_blocks_for_interpretation(
        block_ids: list[str] | None = None,
        file_id: str | None = None,
    ):
        _ = (block_ids, file_id)
        return [
            {"id": "blk-001", "name": "Насос-1", "description": "", "file_id": ""},
            {"id": "blk-002", "name": "Клапан-2", "description": "", "file_id": ""},
        ]

    async def fake_get_full_description(block_name: str, file_id: str | None = None):
        _ = file_id
        return descriptions[block_name]

    async def fake_save_block_description(block_id: str, description: str) -> None:
        _ = (block_id, description)

    async def fake_save_block_interpretations(
        block_id: str,
        short_interpretation: str,
        full_interpretation: str,
        description: str,
    ) -> None:
        _ = (block_id, short_interpretation, full_interpretation, description)

    failing_text = json.dumps(descriptions["Клапан-2"], ensure_ascii=False, sort_keys=True)

    def stub_call(*_args, **kwargs):
        if kwargs["name"] == failing_text:
            raise RuntimeError("timeout")
        if "максимально подробное описание" in kwargs.get("extra_context", ""):
            return "FULL"
        return "SHORT"

    monkeypatch.setattr(
        "parsedwg.db.list_blocks_for_interpretation",
        fake_list_blocks_for_interpretation,
    )
    monkeypatch.setattr(
        "parsedwg.db.get_full_description",
        fake_get_full_description,
    )
    monkeypatch.setattr(
        "parsedwg.db.save_block_description",
        fake_save_block_description,
    )
    monkeypatch.setattr(
        "parsedwg.db.save_block_interpretations",
        fake_save_block_interpretations,
    )
    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.call_ollama_name_meaning",
        stub_call,
    )

    exit_code = main(["interpret-blocks", "--block-id", "blk-001", "--block-id", "blk-002"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "обработан за" in captured.out
    assert "Интерпретировано блоков: 1" in captured.out
    assert "Ошибок: 1" in captured.out


def test_main_interpret_block_by_entity_id(monkeypatch, capsys) -> None:
    captured_args: dict[str, object] = {}
    full_description_payload = {
        "name": "Щит-АВР",
        "attributes": {"PANEL": "AВР"},
    }

    async def fake_list_blocks_for_interpretation(
        block_ids: list[str] | None = None,
        file_id: str | None = None,
    ):
        captured_args["block_ids"] = block_ids
        captured_args["file_id"] = file_id
        return [
            {
                "id": "blk-entity-001",
                "name": "Щит-АВР",
                "description": "",
                "file_id": "",
            }
        ]

    async def fake_get_full_description(block_name: str, file_id: str | None = None):
        captured_args["description_request"] = {
            "block_name": block_name,
            "file_id": file_id,
        }
        return full_description_payload

    async def fake_save_block_description(block_id: str, description: str) -> None:
        captured_args["saved_description"] = {
            "block_id": block_id,
            "description": description,
        }

    async def fake_save_block_interpretations(
        block_id: str,
        short_interpretation: str,
        full_interpretation: str,
        description: str,
    ) -> None:
        captured_args["saved"] = {
            "block_id": block_id,
            "short": short_interpretation,
            "full": full_interpretation,
            "description": description,
        }

    def stub_call(*_args, **kwargs):
        extra_context = kwargs.get("extra_context", "")
        if "максимально подробное описание" in extra_context:
            return f"FULL::{kwargs['name']}"
        return f"SHORT::{kwargs['name']}"

    monkeypatch.setattr(
        "parsedwg.db.list_blocks_for_interpretation",
        fake_list_blocks_for_interpretation,
    )
    monkeypatch.setattr(
        "parsedwg.db.get_full_description",
        fake_get_full_description,
    )
    monkeypatch.setattr(
        "parsedwg.db.save_block_description",
        fake_save_block_description,
    )
    monkeypatch.setattr(
        "parsedwg.db.save_block_interpretations",
        fake_save_block_interpretations,
    )
    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.call_ollama_name_meaning",
        stub_call,
    )

    exit_code = main(["interpret-block", "--entity-id", "blk-entity-001"])
    full_description_text = json.dumps(full_description_payload, ensure_ascii=False, sort_keys=True)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_args["block_ids"] == ["blk-entity-001"]
    assert captured_args["file_id"] is None
    assert captured_args["saved"] == {
        "block_id": "blk-entity-001",
        "short": f"SHORT::{full_description_text}",
        "full": f"FULL::{full_description_text}",
        "description": full_description_text,
    }
    assert "Интерпретировано блоков: 1" in captured.out


def test_main_find_mleader_nearest_outputs_json(monkeypatch, capsys) -> None:
    captured_args: dict[str, object] = {}

    async def fake_list_multileaders_for_nearest_lookup(file_id: str | None = None):
        captured_args["file_id"] = file_id
        return [
            {
                "id": "ml-001",
                "file_id": "file-001",
                "name": "MULTILEADER",
                "source_ref": "/tmp/test.dxf",
                "block": "*Model_Space",
                "layer": "HP_Текст",
            }
        ]

    def fake_collect(
        entities: list[dict[str, str]],
        search_types: tuple[str, ...] = ("LINE", "CIRCLE", "LWPOLYLINE"),
    ):
        captured_args["entities"] = entities
        captured_args["search_types"] = search_types
        return [
            {
                "status": "ok",
                "entity_id": "ml-001",
                "annotation_text": "Поз. 1",
                "nearest_type": "LINE",
                "distance": 0.25,
            }
        ]

    monkeypatch.setattr(
        "parsedwg.db.list_multileaders_for_nearest_lookup",
        fake_list_multileaders_for_nearest_lookup,
    )
    monkeypatch.setattr(
        "parsedwg.cli._collect_mleader_nearest_rows",
        fake_collect,
    )

    exit_code = main([
        "find-mleader-nearest",
        "--search-type",
        "LINE",
        "--search-type",
        "TEXT",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert captured_args["file_id"] is None
    assert captured_args["search_types"] == ("LINE", "TEXT")
    assert payload == [
        {
            "status": "ok",
            "entity_id": "ml-001",
            "annotation_text": "Поз. 1",
            "nearest_type": "LINE",
            "distance": 0.25,
        }
    ]


def test_main_extract_token_tags_requires_tokens_or_drawing(capsys) -> None:
    exit_code = main(["extract-token-tags"])

    _ = capsys.readouterr()
    assert exit_code == 3


def test_main_categorize_entities_by_ids(monkeypatch, capsys) -> None:
    captured_args: dict[str, object] = {}

    async def fake_list_entities_for_semantic_categorization(
        entity_ids: list[str] | None = None,
        entity_type: str | None = None,
    ):
        captured_args["entity_ids"] = entity_ids
        captured_args["entity_type"] = entity_type
        return [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "name": "Насос пожарный",
                "description": "Система пожаротушения",
                "entity_type": "BLOCK",
            }
        ]

    async def fake_assign_semantic_category(
        entity_id: str,
        meanings: list[dict[str, object]],
    ):
        captured_args.setdefault("saved", []).append(
            {
                "entity_id": entity_id,
                "meanings": meanings,
            }
        )
        return {
            "entity_id": entity_id,
            "entity_name": "Насос пожарный",
            "entity_type": "BLOCK",
            "category_id": "22222222-2222-2222-2222-222222222222",
            "category_name": "насос",
            "matched_meaning": "насос",
            "status": "created",
            "meanings": ["насос", "пожаротушение"],
        }

    class StubExtractor:
        def extract_scored_tags(
            self,
            text: str,
            extra_context: str = "",
        ) -> list[dict[str, object]]:
            assert "Насос пожарный" in text
            assert "Система пожаротушения" in text
            assert extra_context == "строительство, чертеж"
            return [
                {"meaning": "насос", "score": 0.93},
                {"meaning": "пожаротушение", "score": 0.58},
            ]

    monkeypatch.setattr(
        "parsedwg.db.list_entities_for_semantic_categorization",
        fake_list_entities_for_semantic_categorization,
    )
    monkeypatch.setattr(
        "parsedwg.db.assign_semantic_category",
        fake_assign_semantic_category,
    )
    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.LangChainNameTagsExtractor.from_config",
        lambda _cfg: StubExtractor(),
    )

    exit_code = main([
        "categorize-entities",
        "--entity-id",
        "11111111-1111-1111-1111-111111111111",
        "--workers",
        "2",
    ])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_args["entity_ids"] == ["11111111-1111-1111-1111-111111111111"]
    assert captured_args["entity_type"] is None
    saved = captured_args["saved"]
    assert isinstance(saved, list)
    assert saved[0]["entity_id"] == "11111111-1111-1111-1111-111111111111"
    assert "Выбрано сущностей: 1" in captured.out
    assert "Сохранено 1/1: 11111111-1111-1111-1111-111111111111 -> насос [created]" in captured.out
    assert "насос" in captured.out
    assert "created" in captured.out


def test_main_categorize_entities_rejects_non_positive_workers(capsys) -> None:
    exit_code = main(["categorize-entities", "--entity-type", "BLOCK", "--workers", "0"])

    _ = capsys.readouterr()
    assert exit_code == 3


def test_main_categorize_entities_saves_one_by_one(monkeypatch, capsys) -> None:
    saved_ids: list[str] = []

    async def fake_list_entities_for_semantic_categorization(
        entity_ids: list[str] | None = None,
        entity_type: str | None = None,
    ):
        _ = entity_ids
        assert entity_type == "BLOCK"
        return [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "name": "Насос",
                "description": "Пожарный",
                "entity_type": "BLOCK",
            },
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "name": "Клапан",
                "description": "Дымоудаление",
                "entity_type": "BLOCK",
            },
        ]

    async def fake_assign_semantic_category(
        entity_id: str,
        meanings: list[dict[str, object]],
    ):
        saved_ids.append(entity_id)
        assert meanings
        return {
            "entity_id": entity_id,
            "entity_name": "stub",
            "entity_type": "BLOCK",
            "category_id": "33333333-3333-3333-3333-333333333333",
            "category_name": str(meanings[0]["meaning"]),
            "matched_meaning": str(meanings[0]["meaning"]),
            "status": "created",
            "meanings": [str(value["meaning"]) for value in meanings],
        }

    class StubExtractor:
        def extract_scored_tags(
            self,
            text: str,
            extra_context: str = "",
        ) -> list[dict[str, object]]:
            assert extra_context == "строительство, чертеж"
            if "Насос" in text:
                return [{"meaning": "насос", "score": 0.9}]
            return [{"meaning": "клапан", "score": 0.8}]

    monkeypatch.setattr(
        "parsedwg.db.list_entities_for_semantic_categorization",
        fake_list_entities_for_semantic_categorization,
    )
    monkeypatch.setattr(
        "parsedwg.db.assign_semantic_category",
        fake_assign_semantic_category,
    )
    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.LangChainNameTagsExtractor.from_config",
        lambda _cfg: StubExtractor(),
    )

    exit_code = main(["categorize-entities", "--entity-type", "BLOCK", "--workers", "2"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert sorted(saved_ids) == [
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    ]
    assert "Выбрано сущностей: 2" in captured.out
    assert "Сохранено 1/2:" in captured.out
    assert "Сохранено 2/2:" in captured.out


def test_main_categorize_entities_requires_single_selection_mode(capsys) -> None:
    exit_code = main(["categorize-entities"])

    _ = capsys.readouterr()
    assert exit_code == 3


def test_main_categorize_entities_by_type_handles_empty_result(monkeypatch, capsys) -> None:
    async def fake_list_entities_for_semantic_categorization(
        entity_ids: list[str] | None = None,
        entity_type: str | None = None,
    ):
        assert entity_ids is None
        assert entity_type == "BLOCK"
        return []

    class StubExtractor:
        def extract_scored_tags(
            self,
            text: str,
            extra_context: str = "",
        ) -> list[dict[str, object]]:
            _ = text
            assert extra_context == "строительство, чертеж"
            return []

    monkeypatch.setattr(
        "parsedwg.db.list_entities_for_semantic_categorization",
        fake_list_entities_for_semantic_categorization,
    )
    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.LangChainNameTagsExtractor.from_config",
        lambda _cfg: StubExtractor(),
    )

    exit_code = main(["categorize-entities", "--entity-type", "BLOCK"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Нет сущностей для категоризации." in captured.out


def test_main_categorize_entities_dry_prints_json_and_skips_db_write(monkeypatch, capsys) -> None:
    async def fake_list_entities_for_semantic_categorization(
        entity_ids: list[str] | None = None,
        entity_type: str | None = None,
    ):
        assert entity_ids is None
        assert entity_type == "BLOCK"
        return [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "name": "Насос",
                "description": "Пожаротушение",
                "entity_type": "BLOCK",
            }
        ]

    async def fake_assign_semantic_category(
        entity_id: str,
        meanings: list[dict[str, object]],
    ):
        _ = entity_id, meanings
        raise AssertionError("assign_semantic_category should not be called in dry mode")

    class StubExtractor:
        def extract_scored_tags(
            self,
            text: str,
            extra_context: str = "",
        ) -> list[dict[str, object]]:
            assert "Насос" in text
            assert extra_context == "строительство, чертеж"
            return [
                {"meaning": "насос", "score": 0.91},
                {"meaning": "пожаротушение", "score": 0.57},
            ]

    monkeypatch.setattr(
        "parsedwg.db.list_entities_for_semantic_categorization",
        fake_list_entities_for_semantic_categorization,
    )
    monkeypatch.setattr(
        "parsedwg.db.assign_semantic_category",
        fake_assign_semantic_category,
    )
    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.LangChainNameTagsExtractor.from_config",
        lambda _cfg: StubExtractor(),
    )

    exit_code = main(["categorize-entities", "--entity-type", "BLOCK", "--dry"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Выбрано сущностей" not in captured.out
    payload = json.loads(captured.out)
    assert payload == [
        {
            "entity_id": "11111111-1111-1111-1111-111111111111",
            "entity_name": "Насос",
            "entity_type": "BLOCK",
            "category_id": "",
            "category_name": "насос",
            "matched_meaning": "насос",
            "status": "dry-run",
            "meanings": [
                {"meaning": "насос", "score": 0.91},
                {"meaning": "пожаротушение", "score": 0.57},
            ],
        }
    ]


def test_main_categorize_entities_dry_empty_result_prints_empty_json(monkeypatch, capsys) -> None:
    async def fake_list_entities_for_semantic_categorization(
        entity_ids: list[str] | None = None,
        entity_type: str | None = None,
    ):
        assert entity_ids is None
        assert entity_type == "BLOCK"
        return []

    class StubExtractor:
        def extract_scored_tags(
            self,
            text: str,
            extra_context: str = "",
        ) -> list[dict[str, object]]:
            _ = text, extra_context
            return []

    monkeypatch.setattr(
        "parsedwg.db.list_entities_for_semantic_categorization",
        fake_list_entities_for_semantic_categorization,
    )
    monkeypatch.setattr(
        "parsedwg.langchain_name_tags.LangChainNameTagsExtractor.from_config",
        lambda _cfg: StubExtractor(),
    )

    exit_code = main(["categorize-entities", "--entity-type", "BLOCK", "--dry"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == []


def test_main_verify_extraction_prints_report(monkeypatch, tmp_path, capsys) -> None:
    source_path = tmp_path / "sample.dxf"
    source_path.write_text("stub", encoding="utf-8")

    async def fake_verify(path: Path, file_id: str | None = None) -> dict[str, object]:
        assert path == source_path
        assert file_id == "11111111-1111-1111-1111-111111111111"
        return {
            "ok": True,
            "file_id": file_id,
            "layouts": {"expected": 1, "actual": 1, "mismatches": []},
            "blocks": {"expected": 1, "actual": 1, "mismatches": []},
            "primitive_counts": {"expected": 2, "actual": 2, "mismatches": []},
            "insert_targets": {"unresolved": []},
            "layer_links": {"missing": []},
            "file_id_check": {"invalid": []},
        }

    monkeypatch.setattr("parsedwg.verify_extraction.verify_extraction", fake_verify)

    exit_code = main([
        "verify-extraction",
        str(source_path),
        "--file-id",
        "11111111-1111-1111-1111-111111111111",
    ])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Проверка file_id=11111111-1111-1111-1111-111111111111" in captured.out
    assert "ИТОГ: ✓ Всё извлечено корректно" in captured.out


def test_main_verify_extraction_returns_not_found(monkeypatch, tmp_path) -> None:
    source_path = tmp_path / "sample.dxf"
    source_path.write_text("stub", encoding="utf-8")

    async def fake_verify(path: Path, file_id: str | None = None) -> dict[str, object]:
        _ = (path, file_id)
        raise LookupError("not found")

    monkeypatch.setattr("parsedwg.verify_extraction.verify_extraction", fake_verify)

    exit_code = main(["verify-extraction", str(source_path)])

    assert exit_code == 2


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


def test_main_project_add_runs_pipeline(monkeypatch, capsys) -> None:
    captured_kwargs: dict[str, object] = {}

    async def fake_create_project(name: str, description: str | None = None, created_by: str | None = None):
        captured_kwargs["name"] = name
        captured_kwargs["description"] = description
        captured_kwargs["created_by"] = created_by
        return {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": name,
            "description": description or "",
            "created_by": created_by or "",
        }

    monkeypatch.setattr("parsedwg.db.create_project", fake_create_project)

    exit_code = main(["project-add", "Башня А", "--description", "Описание", "--created-by", "andrus"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_kwargs["name"] == "Башня А"
    assert captured_kwargs["description"] == "Описание"
    assert captured_kwargs["created_by"] == "andrus"
    assert "Проект создан" in captured.out


def test_main_project_update_runs_pipeline(monkeypatch, capsys) -> None:
    captured_kwargs: dict[str, object] = {}

    async def fake_update_project(
        project_id: str,
        name: str | None = None,
        description: str | None = None,
        created_by: str | None = None,
    ):
        captured_kwargs["project_id"] = project_id
        captured_kwargs["name"] = name
        captured_kwargs["description"] = description
        captured_kwargs["created_by"] = created_by
        return {
            "id": project_id,
            "name": name or "",
            "description": description or "",
            "created_by": created_by or "",
        }

    monkeypatch.setattr("parsedwg.db.update_project", fake_update_project)

    pid = "11111111-1111-1111-1111-111111111111"
    exit_code = main(["project-update", pid, "--name", "Башня Б", "--description", "Новое"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_kwargs["project_id"] == pid
    assert captured_kwargs["name"] == "Башня Б"
    assert captured_kwargs["description"] == "Новое"
    assert "Проект обновлён" in captured.out


def test_main_project_delete_requires_confirmation(monkeypatch, capsys) -> None:
    async def fake_delete_project(project_id: str) -> bool:
        _ = project_id
        return True

    monkeypatch.setattr("parsedwg.db.delete_project", fake_delete_project)
    monkeypatch.setattr("builtins.input", lambda _prompt: "NO")

    pid = "11111111-1111-1111-1111-111111111111"
    exit_code = main(["project-delete", pid])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Удаление отменено." in captured.out


def test_main_project_delete_with_yes(monkeypatch, capsys) -> None:
    captured_kwargs: dict[str, object] = {}

    async def fake_delete_project(project_id: str) -> bool:
        captured_kwargs["project_id"] = project_id
        return True

    monkeypatch.setattr("parsedwg.db.delete_project", fake_delete_project)

    pid = "11111111-1111-1111-1111-111111111111"
    exit_code = main(["project-delete", pid, "--yes"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_kwargs["project_id"] == pid
    assert "Проект удалён" in captured.out


def test_main_category_add_runs_pipeline(monkeypatch, capsys) -> None:
    captured_kwargs: dict[str, object] = {}

    async def fake_create_category(
        name: str,
        description: str | None = None,
        parent_id: str | None = None,
    ):
        captured_kwargs["name"] = name
        captured_kwargs["description"] = description
        captured_kwargs["parent_id"] = parent_id
        return {
            "id": "22222222-2222-2222-2222-222222222222",
            "name": name,
            "description": description or "",
            "parent_id": parent_id or "",
        }

    monkeypatch.setattr("parsedwg.db.create_category", fake_create_category)

    parent_id = "11111111-1111-1111-1111-111111111111"
    exit_code = main([
        "category-add",
        "Архитектура",
        "--description",
        "Разделы по архитектуре",
        "--parent-id",
        parent_id,
    ])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_kwargs["name"] == "Архитектура"
    assert captured_kwargs["description"] == "Разделы по архитектуре"
    assert captured_kwargs["parent_id"] == parent_id
    assert "Категория создана" in captured.out


def test_main_category_update_runs_pipeline(monkeypatch, capsys) -> None:
    captured_kwargs: dict[str, object] = {}

    async def fake_update_category(
        category_id: str,
        name: str | None = None,
        description: str | None = None,
        parent_id: str | None = None,
    ):
        captured_kwargs["category_id"] = category_id
        captured_kwargs["name"] = name
        captured_kwargs["description"] = description
        captured_kwargs["parent_id"] = parent_id
        return {
            "id": category_id,
            "name": name or "",
            "description": description or "",
            "parent_id": parent_id or "",
        }

    monkeypatch.setattr("parsedwg.db.update_category", fake_update_category)

    category_id = "22222222-2222-2222-2222-222222222222"
    exit_code = main([
        "category-update",
        category_id,
        "--name",
        "ОВ",
        "--description",
        "Обновленное описание",
    ])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_kwargs["category_id"] == category_id
    assert captured_kwargs["name"] == "ОВ"
    assert captured_kwargs["description"] == "Обновленное описание"
    assert "Категория обновлена" in captured.out


def test_main_category_delete_requires_confirmation(monkeypatch, capsys) -> None:
    async def fake_delete_category(category_id: str) -> bool:
        _ = category_id
        return True

    monkeypatch.setattr("parsedwg.db.delete_category", fake_delete_category)
    monkeypatch.setattr("builtins.input", lambda _prompt: "NO")

    category_id = "22222222-2222-2222-2222-222222222222"
    exit_code = main(["category-delete", category_id])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Удаление отменено." in captured.out


def test_main_category_delete_with_yes(monkeypatch, capsys) -> None:
    captured_kwargs: dict[str, object] = {}

    async def fake_delete_category(category_id: str) -> bool:
        captured_kwargs["category_id"] = category_id
        return True

    monkeypatch.setattr("parsedwg.db.delete_category", fake_delete_category)

    category_id = "22222222-2222-2222-2222-222222222222"
    exit_code = main(["category-delete", category_id, "--yes"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_kwargs["category_id"] == category_id
    assert "Категория удалена" in captured.out


def test_main_category_list_prints_rows(monkeypatch, capsys) -> None:
    captured_kwargs: dict[str, object] = {}

    async def fake_list_categories(parent_id: str | None = None):
        captured_kwargs["parent_id"] = parent_id
        return [
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "name": "Архитектура",
                "description": "Разделы по архитектуре",
                "parent_id": "",
            }
        ]

    monkeypatch.setattr("parsedwg.db.list_categories", fake_list_categories)

    parent_id = "11111111-1111-1111-1111-111111111111"
    exit_code = main(["category-list", "--parent-id", parent_id])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_kwargs["parent_id"] == parent_id
    assert "Архитектура" in captured.out


def test_main_category_list_handles_empty_result(monkeypatch, capsys) -> None:
    async def fake_list_categories(parent_id: str | None = None):
        _ = parent_id
        return []

    monkeypatch.setattr("parsedwg.db.list_categories", fake_list_categories)

    exit_code = main(["category-list"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Нет категорий." in captured.out
