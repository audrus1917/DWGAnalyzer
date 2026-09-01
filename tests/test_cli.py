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
