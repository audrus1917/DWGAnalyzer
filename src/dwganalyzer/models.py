"""Small domain models shared across DWGAnalyzer boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True, slots=True)
class DrawingSource:
    """Reference to a drawing file or a drawing stored in an archive.

    Args:
        path: Filesystem path to the file or containing archive.
        archive_member: POSIX-style member path when the drawing is archived.
    """

    path: Path
    archive_member: PurePosixPath | None = None

    @property
    def reference(self) -> str:
        """Return a stable human-readable source reference."""

        if self.archive_member is None:
            return str(self.path)
        return f"{self.path}::{self.archive_member.as_posix()}"


@dataclass(frozen=True, slots=True)
class DrawingSummary:
    """Minimal parser-independent summary of a drawing."""

    source: str
    layouts: tuple[str, ...] = ()
    layers: tuple[str, ...] = ()
    blocks: tuple[str, ...] = ()
    entity_count: int = 0
