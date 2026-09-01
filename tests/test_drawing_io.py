import zipfile
from pathlib import Path, PurePosixPath

import ezdxf
import pytest

from dwganalyzer.errors import ConversionError, DrawingReadError, InputError
from dwganalyzer.io.drawings import load_drawing
from dwganalyzer.models import DrawingSource


def _write_dxf(path: Path) -> None:
    drawing = ezdxf.new()
    drawing.modelspace().add_line((0, 0), (10, 10))
    drawing.saveas(path)


def test_loads_dxf_file(tmp_path: Path) -> None:
    source = tmp_path / "drawing.dxf"
    _write_dxf(source)

    drawing = load_drawing(source)

    assert len(drawing.modelspace()) == 1


def test_loads_archived_dxf(tmp_path: Path) -> None:
    dxf_path = tmp_path / "drawing.dxf"
    _write_dxf(dxf_path)
    archive_path = tmp_path / "drawings.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(dxf_path, "nested/drawing.dxf")

    drawing = load_drawing(
        DrawingSource(archive_path, PurePosixPath("nested/drawing.dxf"))
    )

    assert len(drawing.modelspace()) == 1


def test_rejects_corrupted_dxf(tmp_path: Path) -> None:
    source = tmp_path / "broken.dxf"
    source.write_text("not a DXF", encoding="utf-8")

    with pytest.raises(DrawingReadError, match="Unable to read DXF"):
        load_drawing(source)


def test_rejects_missing_drawing(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="Drawing file does not exist"):
        load_drawing(tmp_path / "missing.dxf")


def test_requires_oda_for_dwg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "drawing.dwg"
    source.write_bytes(b"dwg")
    monkeypatch.setattr("dwganalyzer.io.drawings.odafc.is_installed", lambda: False)

    with pytest.raises(ConversionError, match="ODA File Converter is required"):
        load_drawing(source)


def test_delegates_dwg_to_oda(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "drawing.dwg"
    source.write_bytes(b"dwg")
    expected = ezdxf.new()
    received: list[Path] = []

    monkeypatch.setattr("dwganalyzer.io.drawings.odafc.is_installed", lambda: True)

    def fake_readfile(path: Path):
        received.append(path)
        return expected

    monkeypatch.setattr("dwganalyzer.io.drawings.odafc.readfile", fake_readfile)

    assert load_drawing(source) is expected
    assert received == [source]
