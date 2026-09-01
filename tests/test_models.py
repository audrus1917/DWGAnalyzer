from pathlib import Path, PurePosixPath

from dwganalyzer.models import DrawingSource


def test_file_source_reference() -> None:
    source = DrawingSource(path=Path("drawings/plan.dxf"))

    assert source.reference == "drawings/plan.dxf"


def test_archive_source_reference() -> None:
    source = DrawingSource(
        path=Path("drawings/archive.zip"),
        archive_member=PurePosixPath("floor/plan.dwg"),
    )

    assert source.reference == "drawings/archive.zip::floor/plan.dwg"
