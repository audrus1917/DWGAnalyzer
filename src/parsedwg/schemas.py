"""The application dataclasses."""

from typing import Any, Set
from dataclasses import dataclass, field


@dataclass(slots=True)
class BlockDescription:
    """Description of a block, extracted from its name and attributes."""

    block_name: str | None = None
    primitives_layers: Set[Any] = field(default_factory=set)
    nested_blocks: Set[Any] = field(default_factory=set)
    text_content: Set[Any] = field(default_factory=set)
    attdefs: list[Any] = field(default_factory=list)
    insert_samples: list[Any] = field(default_factory=list)