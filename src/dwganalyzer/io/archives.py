"""Safe ZIP archive inspection and drawing extraction."""

from __future__ import annotations

import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from ..errors import ArchiveError
from ..i18n import _
from ..models import DrawingSource

DRAWING_SUFFIXES = frozenset({".dwg", ".dxf"})
_COPY_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ArchiveLimits:
    """Resource limits applied while inspecting and extracting ZIP archives."""

    max_members: int = 10_000
    max_member_size: int = 1024 * 1024 * 1024
    max_total_drawing_size: int = 4 * 1024 * 1024 * 1024
    max_compression_ratio: float = 1_000.0


DEFAULT_ARCHIVE_LIMITS = ArchiveLimits()


def _normalize_member(member_name: str) -> PurePosixPath:
    normalized_name = member_name.replace("\\", "/")
    member = PurePosixPath(normalized_name)
    windows_member = PureWindowsPath(member_name)

    if (
        not member.name
        or member.is_absolute()
        or bool(windows_member.drive)
        or ".." in member.parts
    ):
        raise ArchiveError(
            _("Unsafe ZIP member path: {member}").format(member=member_name)
        )

    return member


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    unix_mode = info.external_attr >> 16
    return stat.S_ISLNK(unix_mode)


def _validate_entry(
    info: zipfile.ZipInfo,
    limits: ArchiveLimits,
) -> PurePosixPath | None:
    if info.is_dir():
        return None

    member = _normalize_member(info.filename)
    if member.suffix.lower() not in DRAWING_SUFFIXES:
        return None

    if info.flag_bits & 0x1:
        raise ArchiveError(
            _("Encrypted ZIP member is not supported: {member}").format(member=member)
        )
    if _is_symlink(info):
        raise ArchiveError(
            _("ZIP member is a symbolic link: {member}").format(member=member)
        )
    if info.file_size > limits.max_member_size:
        raise ArchiveError(
            _("ZIP member is too large: {member}").format(member=member)
        )
    if info.file_size and not info.compress_size:
        raise ArchiveError(
            _("ZIP member has a suspicious compression ratio: {member}").format(
                member=member
            )
        )
    if info.compress_size:
        ratio = info.file_size / info.compress_size
        if ratio > limits.max_compression_ratio:
            raise ArchiveError(
                _("ZIP member has a suspicious compression ratio: {member}").format(
                    member=member
                )
            )

    return member


def _drawing_entries(
    archive_path: Path,
    limits: ArchiveLimits,
) -> dict[PurePosixPath, zipfile.ZipInfo]:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
    except (OSError, zipfile.BadZipFile) as exc:
        raise ArchiveError(
            _("Unable to read ZIP archive: {path}").format(path=archive_path)
        ) from exc

    if len(entries) > limits.max_members:
        raise ArchiveError(
            _("ZIP archive contains too many entries: {path}").format(
                path=archive_path
            )
        )

    drawing_entries: dict[PurePosixPath, zipfile.ZipInfo] = {}
    total_size = 0
    for info in entries:
        member = _validate_entry(info, limits)
        if member is None:
            continue
        if member in drawing_entries:
            raise ArchiveError(
                _("ZIP archive contains duplicate member path: {member}").format(
                    member=member
                )
            )

        drawing_entries[member] = info
        total_size += info.file_size
        if total_size > limits.max_total_drawing_size:
            raise ArchiveError(
                _("ZIP drawing data exceeds the allowed size: {path}").format(
                    path=archive_path
                )
            )

    return drawing_entries


def list_drawing_members(
    archive_path: Path,
    *,
    limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS,
) -> tuple[PurePosixPath, ...]:
    """Return validated drawing members from a ZIP archive.

    Args:
        archive_path: ZIP archive to inspect.
        limits: Resource and compression limits.

    Returns:
        Drawing member paths in deterministic order.

    Raises:
        ArchiveError: If the archive is invalid or violates safety limits.
    """

    entries = _drawing_entries(archive_path, limits)
    return tuple(
        sorted(
            entries,
            key=lambda member: (member.as_posix().casefold(), member.as_posix()),
        )
    )


def extract_drawing(
    source: DrawingSource,
    destination_dir: Path,
    *,
    limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS,
) -> Path:
    """Extract one validated drawing member without preserving archive paths.

    Args:
        source: Archived drawing source.
        destination_dir: Existing or new extraction directory.
        limits: Resource and compression limits.

    Returns:
        Path to the extracted drawing.

    Raises:
        ArchiveError: If the member is missing, unsafe, or cannot be extracted.
    """

    if source.archive_member is None:
        raise ArchiveError(
            _("Drawing source is not an archive member: {source}").format(
                source=source.reference
            )
        )

    requested_member = _normalize_member(source.archive_member.as_posix())
    entries = _drawing_entries(source.path, limits)
    info = entries.get(requested_member)
    if info is None:
        raise ArchiveError(
            _("Drawing was not found in ZIP archive: {source}").format(
                source=source.reference
            )
        )

    destination_dir.mkdir(parents=True, exist_ok=True)
    target = destination_dir / requested_member.name
    if target.exists():
        raise ArchiveError(
            _("Extraction target already exists: {path}").format(path=target)
        )

    bytes_written = 0
    try:
        with zipfile.ZipFile(source.path) as archive:
            with archive.open(info) as input_stream, target.open("xb") as output_stream:
                while chunk := input_stream.read(_COPY_CHUNK_SIZE):
                    bytes_written += len(chunk)
                    if bytes_written > limits.max_member_size:
                        raise ArchiveError(
                            _("ZIP member is too large: {member}").format(
                                member=requested_member
                            )
                        )
                    output_stream.write(chunk)
    except ArchiveError:
        target.unlink(missing_ok=True)
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        target.unlink(missing_ok=True)
        raise ArchiveError(
            _("Unable to extract drawing from ZIP archive: {source}").format(
                source=source.reference
            )
        ) from exc

    if bytes_written != info.file_size:
        target.unlink(missing_ok=True)
        raise ArchiveError(
            _("Unable to extract drawing from ZIP archive: {source}").format(
                source=source.reference
            )
        )

    return target


__all__ = [
    "ArchiveLimits",
    "DEFAULT_ARCHIVE_LIMITS",
    "DRAWING_SUFFIXES",
    "extract_drawing",
    "list_drawing_members",
]
