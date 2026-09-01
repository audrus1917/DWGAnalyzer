"""Render analysis batches for people and machine consumers."""

from __future__ import annotations

import json
from typing import Any

from .i18n import _
from .models import (
    AnalysisBatch,
    AnalysisFinding,
    DrawingAnalysis,
    NamedCount,
)


def _append_counts(
    lines: list[str],
    label: str,
    counts: tuple[NamedCount, ...],
) -> None:
    lines.append(f"{label}:")
    if not counts:
        lines.append(f"  {_('None')}")
        return
    lines.extend(f"  {item.name}: {item.count}" for item in counts)


def _append_names(lines: list[str], label: str, names: tuple[str, ...]) -> None:
    value = ", ".join(names) if names else _("None")
    lines.append(f"{label}: {value}")


def _format_finding(finding: AnalysisFinding) -> str:
    match finding.code:
        case "empty_drawing":
            return _("Drawing contains no entities.")
        case "entity_count_mismatch":
            return _(
                "Entity count mismatch: expected {expected}, found {actual}."
            ).format(
                expected=finding.expected_count,
                actual=finding.actual_count,
            )
        case "layout_entity_count_mismatch":
            return _(
                "Layout {layout} entity count mismatch: expected {expected}, "
                "found {actual}."
            ).format(
                layout=finding.subject,
                expected=finding.expected_count,
                actual=finding.actual_count,
            )
        case "missing_layout_definition":
            return _("Layout definition is missing: {name}.").format(
                name=finding.subject
            )
        case "missing_layer_definition":
            return _("Layer definition is missing: {name}.").format(
                name=finding.subject
            )
        case "missing_block_definition":
            return _("Block definition is missing: {name}.").format(
                name=finding.subject
            )
        case _:
            return _("Analysis finding: {code}.").format(code=finding.code)


def _render_analysis(analysis: DrawingAnalysis) -> list[str]:
    lines = [
        _("Drawing: {source}").format(source=analysis.source),
        _("Entities: {count}").format(count=analysis.entity_count),
        _("Layouts: {count}").format(count=analysis.layout_count),
        _("Layers: {count}").format(count=analysis.layer_count),
        _("Block definitions: {count}").format(
            count=analysis.block_definition_count
        ),
        _("Text entities: {count}").format(count=analysis.text_entity_count),
        _("Block references: {count}").format(
            count=analysis.block_reference_count
        ),
        _("Attributed block references: {count}").format(
            count=analysis.attributed_block_reference_count
        ),
        _("Attributes: {count}").format(count=analysis.attribute_count),
        _("Entities without a layer: {count}").format(
            count=analysis.entities_without_layer
        ),
    ]
    _append_counts(lines, _("Entity types"), analysis.entity_types)
    _append_counts(lines, _("Entities by layout"), analysis.entities_by_layout)
    _append_counts(lines, _("Entities by layer"), analysis.entities_by_layer)
    _append_counts(lines, _("Block reference counts"), analysis.block_references)
    _append_names(lines, _("Used blocks"), analysis.used_blocks)
    _append_names(lines, _("Unused blocks"), analysis.unused_blocks)
    _append_names(lines, _("Missing blocks"), analysis.missing_blocks)
    lines.append(f"{_('Findings')}:")
    if analysis.findings:
        lines.extend(f"  {_format_finding(finding)}" for finding in analysis.findings)
    else:
        lines.append(f"  {_('None')}")
    return lines


def render_text(batch: AnalysisBatch) -> str:
    """Render a localized, human-readable batch report."""

    lines = [
        _("Input: {path}").format(path=batch.input_path),
        _("Drawings discovered: {count}").format(count=batch.discovered_count),
        _("Successfully analyzed: {count}").format(count=len(batch.analyses)),
        _("Failed: {count}").format(count=len(batch.failures)),
    ]
    if not batch.analyses and not batch.failures:
        lines.extend(("", _("No drawings were found.")))

    for analysis in batch.analyses:
        lines.append("")
        lines.extend(_render_analysis(analysis))

    if batch.failures:
        lines.extend(("", f"{_('Failures')}:"))
        lines.extend(
            f"  {failure.source}: {failure.message} [{failure.code}]"
            for failure in batch.failures
        )
    return "\n".join(lines)


def _counts_payload(counts: tuple[NamedCount, ...]) -> list[dict[str, Any]]:
    return [{"name": item.name, "count": item.count} for item in counts]


def _finding_payload(finding: AnalysisFinding) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": finding.code}
    if finding.subject is not None:
        payload["subject"] = finding.subject
    if finding.expected_count is not None:
        payload["expected_count"] = finding.expected_count
    if finding.actual_count is not None:
        payload["actual_count"] = finding.actual_count
    return payload


def _analysis_payload(analysis: DrawingAnalysis) -> dict[str, Any]:
    return {
        "source": analysis.source,
        "entity_count": analysis.entity_count,
        "layout_count": analysis.layout_count,
        "layer_count": analysis.layer_count,
        "block_definition_count": analysis.block_definition_count,
        "text_entity_count": analysis.text_entity_count,
        "block_reference_count": analysis.block_reference_count,
        "attributed_block_reference_count": (
            analysis.attributed_block_reference_count
        ),
        "attribute_count": analysis.attribute_count,
        "entities_without_layer": analysis.entities_without_layer,
        "entity_types": _counts_payload(analysis.entity_types),
        "entities_by_layout": _counts_payload(analysis.entities_by_layout),
        "entities_by_layer": _counts_payload(analysis.entities_by_layer),
        "block_references": _counts_payload(analysis.block_references),
        "used_blocks": list(analysis.used_blocks),
        "unused_blocks": list(analysis.unused_blocks),
        "missing_blocks": list(analysis.missing_blocks),
        "findings": [_finding_payload(item) for item in analysis.findings],
    }


def render_json(batch: AnalysisBatch) -> str:
    """Render a stable, non-localized JSON batch report."""

    payload = {
        "schema_version": 1,
        "input": batch.input_path,
        "summary": {
            "discovered_count": batch.discovered_count,
            "successful_count": len(batch.analyses),
            "failure_count": len(batch.failures),
        },
        "drawings": [_analysis_payload(item) for item in batch.analyses],
        "failures": [
            {"source": failure.source, "code": failure.code}
            for failure in batch.failures
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


__all__ = ["render_json", "render_text"]
