import zipfile
from pathlib import Path

import pytest

from dwganalyzer.errors import ArchiveError, InputError
from dwganalyzer.i18n import using_language
from dwganalyzer.io.discovery import discover_sources


def test_discovers_directory_sources(tmp_path: Path) -> None:
    drawings = tmp_path / "drawings"
    nested = drawings / "nested"
    nested.mkdir(parents=True)
    (drawings / "B.dwg").write_bytes(b"dwg")
    (nested / "a.DXF").write_bytes(b"dxf")
    (nested / "ignore.txt").write_text("ignore", encoding="utf-8")
    archive_path = drawings / "archive.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("inside/c.dxf", b"dxf")

    sources = discover_sources(drawings)

    assert [source.reference for source in sources] == sorted(
        [
            str(drawings / "B.dwg"),
            f"{archive_path}::inside/c.dxf",
            str(nested / "a.DXF"),
        ],
        key=lambda value: (value.casefold(), value),
    )


def test_discovers_direct_archive(tmp_path: Path) -> None:
    archive_path = tmp_path / "drawings.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("plan.dwg", b"dwg")

    sources = discover_sources(archive_path)

    assert len(sources) == 1
    assert sources[0].reference == f"{archive_path}::plan.dwg"


def test_missing_input_is_localized(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    with using_language("ru"):
        with pytest.raises(InputError, match="Входной путь не существует"):
            discover_sources(missing)


def test_rejects_unsupported_file(tmp_path: Path) -> None:
    source = tmp_path / "drawing.txt"
    source.write_text("not a drawing", encoding="utf-8")

    with pytest.raises(InputError, match="Unsupported input type"):
        discover_sources(source)


def test_rejects_corrupted_archive(tmp_path: Path) -> None:
    archive_path = tmp_path / "broken.zip"
    archive_path.write_bytes(b"not a zip")

    with pytest.raises(ArchiveError, match="Unable to read ZIP archive"):
        discover_sources(archive_path)
