import stat
import zipfile
from pathlib import Path, PurePosixPath

import pytest

from dwganalyzer.errors import ArchiveError
from dwganalyzer.io.archives import (
    ArchiveLimits,
    extract_drawing,
    list_drawing_members,
)
from dwganalyzer.models import DrawingSource


def test_lists_and_extracts_drawings(tmp_path: Path) -> None:
    archive_path = tmp_path / "drawings.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("nested/PLAN.DXF", b"drawing-data")
        archive.writestr("notes/readme.txt", b"ignore")

    members = list_drawing_members(archive_path)
    extracted = extract_drawing(
        DrawingSource(archive_path, members[0]),
        tmp_path / "extracted",
    )

    assert members == (PurePosixPath("nested/PLAN.DXF"),)
    assert extracted.name == "PLAN.DXF"
    assert extracted.read_bytes() == b"drawing-data"


def test_rejects_traversal_member(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../plan.dxf", b"drawing-data")

    with pytest.raises(ArchiveError, match="Unsafe ZIP member path"):
        list_drawing_members(archive_path)


def test_rejects_large_member(tmp_path: Path) -> None:
    archive_path = tmp_path / "large.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("plan.dxf", b"1234")

    limits = ArchiveLimits(max_member_size=3)
    with pytest.raises(ArchiveError, match="ZIP member is too large"):
        list_drawing_members(archive_path, limits=limits)


def test_rejects_symlink_member(tmp_path: Path) -> None:
    archive_path = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("plan.dxf")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, "target.dxf")

    with pytest.raises(ArchiveError, match="symbolic link"):
        list_drawing_members(archive_path)


def test_does_not_overwrite_target(tmp_path: Path) -> None:
    archive_path = tmp_path / "drawings.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("plan.dxf", b"new")

    destination = tmp_path / "extracted"
    destination.mkdir()
    target = destination / "plan.dxf"
    target.write_bytes(b"existing")
    source = DrawingSource(archive_path, PurePosixPath("plan.dxf"))

    with pytest.raises(ArchiveError, match="already exists"):
        extract_drawing(source, destination)
    assert target.read_bytes() == b"existing"
