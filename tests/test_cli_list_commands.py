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


def test_main_process_runs_pipeline(tmp_path, monkeypatch, capsys) -> None:
    source_dir = tmp_path / "tower_A"
    source_dir.mkdir(parents=True)

    captured_args: dict[str, object] = {}

    def fake_run(
        source_path: Path,
        conversion_workers: int = 2,
        name_tags_config: dict[str, str] | None = None,
        **kwargs,
    ) -> dict[str, object]:
        project_name = kwargs.get("project_name")
        project_description = kwargs.get("project_description")
        created_by = kwargs.get("created_by")
        captured_args["source_path"] = source_path
        captured_args["conversion_workers"] = conversion_workers
        captured_args["project_name"] = project_name
        captured_args["project_description"] = project_description
        captured_args["created_by"] = created_by
        captured_args["name_tags_config"] = name_tags_config
        return {
            "project_id": "11111111-1111-1111-1111-111111111111",
            "file_count": 3,
            "processed_count": 3,
            "created_entities": 42,
        }

    monkeypatch.setattr("parsedwg.cli.run_process_tree", fake_run)

    exit_code = main(
        [
            "process",
            str(source_dir),
            "--workers",
            "2",
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
    assert captured_args["conversion_workers"] == 2
    assert captured_args["project_name"] == "Башня А"
    assert captured_args["project_description"] == "Тестовый проект"
    assert captured_args["created_by"] == "andrus"
    assert captured_args["name_tags_config"] is None
    assert "Найдено файлов: 3" in captured.out
    assert "Обработано файлов: 3" in captured.out
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
        conversion_workers: int = 2,
        name_tags_config: dict[str, str] | None = None,
        **kwargs,
    ) -> dict[str, object]:
        _ = kwargs
        captured_args["source_path"] = source_path
        captured_args["conversion_workers"] = conversion_workers
        captured_args["name_tags_config"] = name_tags_config
        return {
            "project_id": "11111111-1111-1111-1111-111111111111",
            "file_count": 1,
            "processed_count": 1,
            "created_entities": 10,
        }

    monkeypatch.setattr("parsedwg.cli._build_name_tags_config", fake_config_builder)
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
    assert captured_args["conversion_workers"] == 1
    assert captured_args["name_tags_config"] == {
        "model": "llama3.1:70b",
        "base_url": "http://localhost:11434/v1",
        "api_key": "secret",
    }


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
        "parsedwg.cli._build_name_tags_config",
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
