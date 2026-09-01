"""Discover drawing sources in files, directories, and ZIP archives."""

from __future__ import annotations

from pathlib import Path

from ..errors import InputError
from ..i18n import _
from ..models import DrawingSource
from .archives import DRAWING_SUFFIXES, list_drawing_members


def _sources_from_archive(archive_path: Path) -> list[DrawingSource]:
    return [
        DrawingSource(path=archive_path, archive_member=member)
        for member in list_drawing_members(archive_path)
    ]


def _sort_sources(sources: list[DrawingSource]) -> tuple[DrawingSource, ...]:
    return tuple(
        sorted(
            sources,
            key=lambda source: (source.reference.casefold(), source.reference),
        )
    )


def discover_sources(input_path: str | Path) -> tuple[DrawingSource, ...]:
    """Discover supported drawing sources below a filesystem path.

    Args:
        input_path: DWG/DXF file, ZIP archive, or directory to inspect.

    Returns:
        Drawing sources in deterministic order.

    Raises:
        InputError: If the input is missing or has an unsupported type.
        ArchiveError: If a ZIP archive is invalid or unsafe.
    """

    path = Path(input_path)
    if not path.exists():
        raise InputError(_("Input path does not exist: {path}").format(path=path))

    if path.is_file():
        suffix = path.suffix.lower()
        if suffix in DRAWING_SUFFIXES:
            return (DrawingSource(path=path),)
        if suffix == ".zip":
            return tuple(_sources_from_archive(path))
        raise InputError(_("Unsupported input type: {path}").format(path=path))

    if not path.is_dir():
        raise InputError(_("Unsupported input type: {path}").format(path=path))

    sources: list[DrawingSource] = []
    entries = sorted(
        (entry for entry in path.rglob("*") if not entry.is_symlink()),
        key=lambda entry: (entry.as_posix().casefold(), entry.as_posix()),
    )
    for entry in entries:
        if not entry.is_file():
            continue
        suffix = entry.suffix.lower()
        if suffix in DRAWING_SUFFIXES:
            sources.append(DrawingSource(path=entry))
        elif suffix == ".zip":
            sources.extend(_sources_from_archive(entry))

    return _sort_sources(sources)


__all__ = ["discover_sources"]
