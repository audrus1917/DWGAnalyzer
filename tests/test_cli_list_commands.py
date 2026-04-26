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
        def extract_token_meanings_json(self, tokens: list[str]) -> str:
            assert tokens == ["M_Doors", "M_Wall_Glass"]
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
        def extract_token_meanings_json(self, tokens: list[str]) -> str:
            assert "M_Doors" in tokens
            assert "M_Wall_Glass" in tokens
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
        def extract_token_meanings_scored_json(self, tokens: list[str]) -> str:
            assert tokens == ["M_Doors"]
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


def test_main_extract_token_tags_requires_tokens_or_drawing(capsys) -> None:
    exit_code = main(["extract-token-tags"])

    _ = capsys.readouterr()
    assert exit_code == 3


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
