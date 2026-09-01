"""Analyze drawing inventories without depending on parser objects."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from ..models import (
    AnalysisFinding,
    BlockSummary,
    DrawingAnalysis,
    DrawingSummary,
    NamedCount,
)


def _sort_names(names: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(names, key=lambda name: (name.casefold(), name)))


def _count_names(names: Iterable[str | None]) -> tuple[NamedCount, ...]:
    counts = Counter(name for name in names if name is not None)
    return tuple(
        NamedCount(name=name, count=counts[name])
        for name in _sort_names(counts)
    )


def _block_inventory(
    summary: DrawingSummary,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    blocks_by_name: dict[str, BlockSummary] = {
        block.name: block for block in summary.blocks
    }
    defined_names = set(blocks_by_name)
    layout_references = {
        entity.block_name
        for entity in summary.entities
        if entity.block_name is not None
    }
    nested_references = {
        nested_name
        for block in summary.blocks
        for nested_name in block.nested_blocks
    }

    reachable_names: set[str] = set()
    pending_names = list(layout_references)
    while pending_names:
        block_name = pending_names.pop()
        if block_name in reachable_names:
            continue
        reachable_names.add(block_name)
        block = blocks_by_name.get(block_name)
        if block is not None:
            pending_names.extend(block.nested_blocks)

    used_blocks = defined_names & reachable_names
    unused_blocks = defined_names - used_blocks
    missing_blocks = (layout_references | nested_references) - defined_names
    return (
        _sort_names(used_blocks),
        _sort_names(unused_blocks),
        _sort_names(missing_blocks),
    )


def _consistency_findings(
    summary: DrawingSummary,
    *,
    missing_blocks: tuple[str, ...],
) -> tuple[AnalysisFinding, ...]:
    findings: list[AnalysisFinding] = []
    actual_entity_count = len(summary.entities)
    if actual_entity_count == 0:
        findings.append(AnalysisFinding(code="empty_drawing"))

    if summary.entity_count != actual_entity_count:
        findings.append(
            AnalysisFinding(
                code="entity_count_mismatch",
                expected_count=summary.entity_count,
                actual_count=actual_entity_count,
            )
        )

    layout_entity_counts = Counter(entity.layout for entity in summary.entities)
    layout_names = {layout.name for layout in summary.layouts}
    for layout in summary.layouts:
        actual_count = layout_entity_counts[layout.name]
        if layout.entity_count != actual_count:
            findings.append(
                AnalysisFinding(
                    code="layout_entity_count_mismatch",
                    subject=layout.name,
                    expected_count=layout.entity_count,
                    actual_count=actual_count,
                )
            )

    for layout_name in _sort_names(set(layout_entity_counts) - layout_names):
        findings.append(
            AnalysisFinding(code="missing_layout_definition", subject=layout_name)
        )

    layer_names = {layer.name for layer in summary.layers}
    referenced_layers = {
        entity.layer for entity in summary.entities if entity.layer is not None
    }
    for layer_name in _sort_names(referenced_layers - layer_names):
        findings.append(
            AnalysisFinding(code="missing_layer_definition", subject=layer_name)
        )

    findings.extend(
        AnalysisFinding(code="missing_block_definition", subject=block_name)
        for block_name in missing_blocks
    )
    return tuple(findings)


def analyze_drawing(summary: DrawingSummary) -> DrawingAnalysis:
    """Build an inventory and structural consistency analysis.

    Args:
        summary: Parser-independent drawing data.

    Returns:
        Aggregate counts, block reachability, and machine-readable findings.
    """

    used_blocks, unused_blocks, missing_blocks = _block_inventory(summary)
    block_references = tuple(
        entity for entity in summary.entities if entity.block_name is not None
    )
    attributed_references = tuple(
        entity for entity in block_references if entity.attributes
    )
    return DrawingAnalysis(
        source=summary.source,
        entity_count=len(summary.entities),
        layout_count=len(summary.layouts),
        layer_count=len(summary.layers),
        block_definition_count=len(summary.blocks),
        text_entity_count=sum(
            entity.text is not None for entity in summary.entities
        ),
        block_reference_count=len(block_references),
        attributed_block_reference_count=len(attributed_references),
        attribute_count=sum(
            len(entity.attributes) for entity in block_references
        ),
        entities_without_layer=sum(
            entity.layer is None for entity in summary.entities
        ),
        entity_types=_count_names(
            entity.entity_type for entity in summary.entities
        ),
        entities_by_layout=_count_names(
            entity.layout for entity in summary.entities
        ),
        entities_by_layer=_count_names(
            entity.layer for entity in summary.entities
        ),
        block_references=_count_names(
            entity.block_name for entity in block_references
        ),
        used_blocks=used_blocks,
        unused_blocks=unused_blocks,
        missing_blocks=missing_blocks,
        findings=_consistency_findings(
            summary,
            missing_blocks=missing_blocks,
        ),
    )


__all__ = ["analyze_drawing"]
