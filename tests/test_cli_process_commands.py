from pathlib import Path

from parsedwg.cli import main


def test_main_process_runs_handler(tmp_path, monkeypatch) -> None:
    source_dir = tmp_path / "tower_A"
    source_dir.mkdir(parents=True)
    captured_args: dict[str, object] = {}

    def fake_handle_process_command(
        source_path: Path,
        project_name: str | None,
        dry: bool = False,
        detail_level: str = "high",
    ) -> int:
        captured_args["source_path"] = source_path
        captured_args["project_name"] = project_name
        captured_args["dry"] = dry
        captured_args["detail_level"] = detail_level
        return 0

    monkeypatch.setattr("parsedwg.cli.handle_process_command", fake_handle_process_command)

    exit_code = main(["process", str(source_dir), "--project", "Башня А"])

    assert exit_code == 0
    assert captured_args == {
        "source_path": source_dir,
        "project_name": "Башня А",
        "dry": False,
        "detail_level": "high",
    }


def test_main_process_dry_runs_handler_without_project(tmp_path, monkeypatch) -> None:
    source_dir = tmp_path / "tower_A"
    source_dir.mkdir(parents=True)
    captured_args: dict[str, object] = {}

    def fake_handle_process_command(
        source_path: Path,
        project_name: str | None,
        dry: bool = False,
        detail_level: str = "high",
    ) -> int:
        captured_args["source_path"] = source_path
        captured_args["project_name"] = project_name
        captured_args["dry"] = dry
        captured_args["detail_level"] = detail_level
        return 0

    monkeypatch.setattr("parsedwg.cli.handle_process_command", fake_handle_process_command)

    exit_code = main(["process", str(source_dir), "--dry"])

    assert exit_code == 0
    assert captured_args == {
        "source_path": source_dir,
        "project_name": None,
        "dry": True,
        "detail_level": "high",
    }


def test_main_process_passes_detail_level(tmp_path, monkeypatch) -> None:
    source_dir = tmp_path / "tower_A"
    source_dir.mkdir(parents=True)
    captured_args: dict[str, object] = {}

    def fake_handle_process_command(
        source_path: Path,
        project_name: str | None,
        dry: bool = False,
        detail_level: str = "high",
    ) -> int:
        captured_args["source_path"] = source_path
        captured_args["project_name"] = project_name
        captured_args["dry"] = dry
        captured_args["detail_level"] = detail_level
        return 0

    monkeypatch.setattr("parsedwg.cli.handle_process_command", fake_handle_process_command)

    exit_code = main([
        "process",
        str(source_dir),
        "--project",
        "Башня А",
        "--detail-level",
        "medium",
    ])

    assert exit_code == 0
    assert captured_args["detail_level"] == "medium"


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

    assert exit_code == 0
    assert captured_args["source_path"] == source_dir
    output = capsys.readouterr().out
    assert "Найдено документов: 4" in output
    assert "Создано сущностей в БД: 4" in output


def test_handle_process_command_prints_summary(tmp_path, monkeypatch, capsys) -> None:
    from parsedwg.cli import handle_process_command

    source_dir = tmp_path / "tower_A"
    source_dir.mkdir(parents=True)

    def fake_process_source(
        source_path: Path,
        project_name: str | None,
        dry: bool = False,
        detail_level: str = "high",
    ) -> dict[str, object]:
        assert source_path == source_dir
        assert project_name == "Башня А"
        assert dry is False
        assert detail_level == "high"
        return {
            "file_count": 3,
            "mode": "direct",
            "detail_level": detail_level,
            "created_entities": 42,
        }

    monkeypatch.setattr("src.parsedwg.commands.process.process_source", fake_process_source)

    exit_code = handle_process_command(source_dir, project_name="Башня А")

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Найдено файлов: 3" in output
    assert "Режим обработки: direct" in output
    assert "Создано сущностей в БД: 42" in output


def test_handle_process_command_prints_dry_summary(tmp_path, monkeypatch, capsys) -> None:
    from parsedwg.cli import handle_process_command

    source_dir = tmp_path / "tower_A"
    source_dir.mkdir(parents=True)

    def fake_process_source(
        source_path: Path,
        project_name: str | None,
        dry: bool = False,
        detail_level: str = "high",
    ) -> dict[str, object]:
        assert source_path == source_dir
        assert project_name is None
        assert dry is True
        assert detail_level == "high"
        return {
            "file_count": 3,
            "mode": "dry",
            "detail_level": detail_level,
            "created_entities": 0,
        }

    monkeypatch.setattr("src.parsedwg.commands.process.process_source", fake_process_source)

    exit_code = handle_process_command(source_dir, project_name=None, dry=True)

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Найдено файлов: 3" in output
    assert "Режим обработки: dry" in output
    assert "Создано сущностей в БД: 0" in output