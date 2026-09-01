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
class LayoutSummary:
    """Parser-independent layout metadata."""

    name: str
    is_modelspace: bool
    tab_order: int
    entity_count: int


@dataclass(frozen=True, slots=True)
class LayerSummary:
    """Parser-independent layer metadata."""

    name: str
    color: int
    linetype: str
    lineweight: int
    is_on: bool
    is_frozen: bool
    is_locked: bool


@dataclass(frozen=True, slots=True)
class AttributeValue:
    """Tag and value attached to a block reference."""

    tag: str
    value: str


@dataclass(frozen=True, slots=True)
class AttributeDefinition:
    """Attribute definition declared by a block."""

    tag: str
    prompt: str
    default: str


@dataclass(frozen=True, slots=True)
class BlockSummary:
    """Direct metadata from a block definition."""

    name: str
    entity_count: int
    layers: tuple[str, ...] = ()
    nested_blocks: tuple[str, ...] = ()
    text: tuple[str, ...] = ()
    attribute_definitions: tuple[AttributeDefinition, ...] = ()


@dataclass(frozen=True, slots=True)
class EntitySummary:
    """Normalized representation of an entity placed in a layout."""

    entity_type: str
    layout: str
    layer: str | None = None
    text: str | None = None
    block_name: str | None = None
    attributes: tuple[AttributeValue, ...] = ()


@dataclass(frozen=True, slots=True)
class DrawingSummary:
    """Parser-independent drawing metadata and layout entities."""

    source: str
    layouts: tuple[LayoutSummary, ...] = ()
    layers: tuple[LayerSummary, ...] = ()
    blocks: tuple[BlockSummary, ...] = ()
    entities: tuple[EntitySummary, ...] = ()
    entity_count: int = 0
