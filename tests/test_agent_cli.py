from pathlib import Path

from parsedwg.cli import main


def test_main_agent_run_invokes_agent_service(tmp_path, monkeypatch, capsys) -> None:
    source_path = tmp_path / "sample.dxf"
    source_path.write_text("stub", encoding="utf-8")

    captured_args: dict[str, object] = {}

    def fake_run_agent_job_sync(
        input_ref: str,
        profile: str,
        ai_model: str,
        ai_base_url: str,
        ai_api_key: str,
        workers: int,
        dry: bool,
        project_name: str | None = None,
    ) -> int:
        captured_args["input_ref"] = input_ref
        captured_args["profile"] = profile
        captured_args["ai_model"] = ai_model
        captured_args["ai_base_url"] = ai_base_url
        captured_args["ai_api_key"] = ai_api_key
        captured_args["workers"] = workers
        captured_args["dry"] = dry
        captured_args["project_name"] = project_name
        return 17

    monkeypatch.setattr("parsedwg.agent_service.run_agent_job_sync", fake_run_agent_job_sync)

    exit_code = main(
        [
            "agent-run",
            str(source_path),
            "--profile",
            "full",
            "--workers",
            "2",
            "--dry",
            "--project",
            "Башня А",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_args["input_ref"] == str(source_path)
    assert captured_args["profile"] == "full"
    assert captured_args["workers"] == 2
    assert captured_args["dry"] is True
    assert captured_args["project_name"] == "Башня А"
    assert "Агентная задача завершена: 17" in captured.out


def test_main_agent_status_prints_steps(monkeypatch, capsys) -> None:
    def fake_get_agent_job_report(job_id: int) -> dict[str, object] | None:
        assert job_id == 17
        return {
            "job": {
                "id": 17,
                "status": "completed",
                "profile": "full",
                "input_ref": "_data/sample.dxf",
                "file_id": 11,
                "error_message": None,
            },
            "steps": [
                {
                    "step_order": 1,
                    "step_kind": "interpret_blocks",
                    "status": "completed",
                    "error_message": None,
                    "result_json": {"processed": 3, "failed": 0},
                },
                {
                    "step_order": 2,
                    "step_kind": "verify_extraction",
                    "status": "skipped",
                    "error_message": None,
                    "result_json": None,
                },
            ],
        }

    monkeypatch.setattr("parsedwg.agent_service.get_agent_job_report", fake_get_agent_job_report)

    exit_code = main(["agent-status", "17"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Agent job: 17" in captured.out
    assert "1. interpret_blocks: completed" in captured.out
    assert "2. verify_extraction: skipped" in captured.out