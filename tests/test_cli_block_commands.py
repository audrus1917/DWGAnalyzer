import json
from pathlib import Path

from parsedwg.cli import main


def test_main_extract_block_runs_explorer(tmp_path, monkeypatch) -> None:
    source_path = tmp_path / "sample.dxf"
    source_path.write_text("stub", encoding="utf-8")
    captured_args: dict[str, object] = {}

    class StubExplorer:
        def __init__(self, drawing: Path):
            captured_args["drawing"] = drawing

        def extract_block(self, block_name: str) -> int:
            captured_args["block_name"] = block_name
            return 0

    monkeypatch.setattr("parsedwg.cli.DXFExplorer", StubExplorer)

    exit_code = main(["extract-block", str(source_path), "BLOCK_A"])

    assert exit_code == 0
    assert captured_args == {"drawing": source_path, "block_name": "BLOCK_A"}


def test_main_describe_block_outputs_json(tmp_path, monkeypatch, capsys) -> None:
    source_path = tmp_path / "sample.dxf"
    source_path.write_text("stub", encoding="utf-8")
    payload = {
        "drawing": str(source_path),
        "block": "BLOCK_A",
        "description": "Сущностей: 2. Вставок: 1",
        "entities": [{"type": "LINE"}],
    }

    class StubExplorer:
        def __init__(self, drawing: Path):
            assert drawing == source_path

        def describe_block(self, block_name: str) -> dict[str, object]:
            assert block_name == "BLOCK_A"
            return payload

    monkeypatch.setattr("parsedwg.cli.DXFExplorer", StubExplorer)

    exit_code = main(["describe-block", str(source_path), "BLOCK_A"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == payload


def test_main_describe_block_writes_json_file(tmp_path, monkeypatch, capsys) -> None:
    source_path = tmp_path / "sample.dxf"
    source_path.write_text("stub", encoding="utf-8")
    output_path = tmp_path / "block.json"
    payload = {"block": "BLOCK_A", "entities": [{"type": "TEXT", "text": "A"}]}

    class StubExplorer:
        def __init__(self, drawing: Path):
            assert drawing == source_path

        def describe_block(self, block_name: str) -> dict[str, object]:
            assert block_name == "BLOCK_A"
            return payload

    monkeypatch.setattr("parsedwg.cli.DXFExplorer", StubExplorer)

    exit_code = main(["describe-block", str(source_path), "BLOCK_A", "-o", str(output_path)])

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8")) == payload
    assert capsys.readouterr().out == ""


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

    exit_code = main([
        "export-block-png",
        str(source_path),
        "BLOCK_A",
        "-o",
        str(target_path),
        "--dpi",
        "200",
    ])

    assert exit_code == 0
    assert captured_args == {
        "drawing": source_path,
        "block_name": "BLOCK_A",
        "output_path": target_path,
        "dpi": 200,
    }
    assert f"PNG сохранён: {target_path}" in capsys.readouterr().out