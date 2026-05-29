from pathlib import Path

import pytest

from parsedwg.cli import main
from parsedwg.cli import handle_plot_entity_geom_command


def test_main_project_list_prints_rows(monkeypatch, capsys) -> None:
    async def fake_list_projects():
        return [
            {
                "id": "1",
                "name": "Башня А",
                "description": "Описание",
                "created_by": "andrus",
                "created_at": "2026-05-25T10:00:00+00:00",
            }
        ]

    monkeypatch.setattr("parsedwg.db.list_projects", fake_list_projects)

    exit_code = main(["project-list"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Башня А" in output
    assert "created_by" in output


def test_main_file_list_passes_project_filter(monkeypatch, capsys) -> None:
    captured_kwargs: dict[str, object] = {}

    async def fake_list_file_entities(project_name: str | None = None):
        captured_kwargs["project_name"] = project_name
        return [
            {
                "id": "10",
                "name": "sheet-01.dxf",
                "project_id": "1",
                "project": "Башня А",
                "source_ref": "/tmp/sheet-01.dxf",
                "created_at": "2026-05-25T10:00:00+00:00",
            }
        ]

    monkeypatch.setattr("parsedwg.db.list_file_entities", fake_list_file_entities)

    exit_code = main(["file-list", "--project", "Башня А"])

    assert exit_code == 0
    assert captured_kwargs == {"project_name": "Башня А"}
    output = capsys.readouterr().out
    assert "sheet-01.dxf" in output
    assert "Башня А" in output


def test_main_entity_list_passes_filters(monkeypatch, capsys) -> None:
    captured_kwargs: dict[str, object] = {}

    async def fake_list_entities_for_cli(
        entity_type: str,
        project_name: str | None = None,
        file_id: str | None = None,
    ):
        captured_kwargs["entity_type"] = entity_type
        captured_kwargs["project_name"] = project_name
        captured_kwargs["file_id"] = file_id
        return [
            {
                "id": "20",
                "name": "Насос",
                "description": "Блок оборудования",
                "entity_type": entity_type,
                "file_id": file_id or "10",
                "file_name": "sheet-01.dxf",
                "project_id": "1",
                "project": project_name or "Башня А",
                "created_at": "2026-05-25T10:00:00+00:00",
            }
        ]

    monkeypatch.setattr("parsedwg.db.list_entities_for_cli", fake_list_entities_for_cli)

    exit_code = main([
        "entity-list",
        "--entity-type",
        "BLOCK",
        "--project",
        "Башня А",
        "--file-id",
        "10",
    ])

    assert exit_code == 0
    assert captured_kwargs == {
        "entity_type": "BLOCK",
        "project_name": "Башня А",
        "file_id": "10",
    }
    output = capsys.readouterr().out
    assert "Насос" in output
    assert "sheet-01.dxf" in output


def test_main_entity_list_handles_invalid_entity_type(monkeypatch, capsys) -> None:
    async def fake_list_entities_for_cli(
        entity_type: str,
        project_name: str | None = None,
        file_id: str | None = None,
    ):
        _ = project_name
        _ = file_id
        raise ValueError(f"Unknown entity type: {entity_type}")

    monkeypatch.setattr("parsedwg.db.list_entities_for_cli", fake_list_entities_for_cli)

    exit_code = main(["entity-list", "--entity-type", "NOPE"])

    assert exit_code == 1
    assert "Unknown entity type: NOPE" in capsys.readouterr().out


def test_main_plot_entity_geom_passes_ids_and_output(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_handle_plot_entity_geom_command(
        entity_ids: list[str],
        output_path: Path | None,
    ) -> int:
        captured["entity_ids"] = entity_ids
        captured["output_path"] = output_path
        return 0

    monkeypatch.setattr(
        "parsedwg.cli.handle_plot_entity_geom_command",
        fake_handle_plot_entity_geom_command,
    )

    output_path = tmp_path / "entities.png"
    exit_code = main(["plot-entity-geom", "101", "102", "-o", str(output_path)])

    assert exit_code == 0
    assert captured == {
        "entity_ids": ["101", "102"],
        "output_path": output_path,
    }


def test_handle_plot_entity_geom_command_writes_image(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("matplotlib")
    pytest.importorskip("shapely")

    async def fake_list_entity_geometries(entity_ids: list[str]) -> list[dict[str, str]]:
        assert entity_ids == ["101", "102"]
        return [
            {
                "id": "101",
                "name": "Line",
                "entity_type": "PRIMITIVE",
                "geom": "LINESTRING (0 0, 10 0, 10 5)",
            },
            {
                "id": "102",
                "name": "Roof",
                "entity_type": "PRIMITIVE",
                "geom": "POLYGON ((0 0, 4 0, 4 3, 0 0))",
            },
        ]

    monkeypatch.setattr("parsedwg.db.list_entity_geometries", fake_list_entity_geometries)

    output_path = tmp_path / "entities.png"
    exit_code = handle_plot_entity_geom_command(["101", "102"], output_path)

    assert exit_code == 0
    assert output_path.exists()
    assert output_path.stat().st_size > 0