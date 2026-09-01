import json
from pathlib import Path

import ezdxf
import pytest

from dwganalyzer.cli import main
from dwganalyzer.i18n import using_language


def test_cli_shows_english_help(capsys: pytest.CaptureFixture[str]) -> None:
    with using_language("en"):
        result = main([])

    assert result == 0
    assert "DWG/DXF drawing analyzer" in capsys.readouterr().out


def test_cli_reports_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out == "dwganalyzer 0.1.0\n"


def test_cli_shows_russian_help(capsys: pytest.CaptureFixture[str]) -> None:
    with using_language("ru"):
        result = main([])

    output = capsys.readouterr().out
    assert result == 0
    assert "Анализатор чертежей DWG/DXF" in output
    assert "Показать это справочное сообщение и выйти." in output


def test_cli_analyzes_dxf(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "drawing.dxf"
    drawing = ezdxf.new()
    drawing.modelspace().add_circle((0, 0), radius=5)
    drawing.saveas(source)

    result = main(["analyze", str(source)])

    assert result == 0
    output = capsys.readouterr().out
    assert f"Drawing: {source}" in output
    assert "Entities: 1" in output
    assert "CIRCLE: 1" in output


def test_cli_outputs_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "drawing.dxf"
    drawing = ezdxf.new()
    drawing.saveas(source)

    result = main(["analyze", str(source), "--format", "json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["successful_count"] == 1
    assert payload["drawings"][0]["source"] == str(source)


def test_cli_reports_input_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing.dxf"

    result = main(["analyze", str(missing)])

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert "Error: Input path does not exist" in captured.err


def test_cli_reports_drawing_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "broken.dxf"
    source.write_text("not a DXF", encoding="utf-8")

    result = main(["analyze", str(source)])

    captured = capsys.readouterr()
    assert result == 1
    assert "Failed: 1" in captured.out
    assert "[drawing_read_error]" in captured.out
    assert captured.err == ""


def test_cli_selects_russian(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "drawing.dxf"
    drawing = ezdxf.new()
    drawing.saveas(source)

    result = main(["analyze", str(source), "--language", "ru"])

    assert result == 0
    assert "Найдено чертежей: 1" in capsys.readouterr().out
