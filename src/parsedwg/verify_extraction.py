"""Verify that a DWG/DXF file is stored correctly in the current database."""

from __future__ import annotations

import uuid
import logging

from collections import defaultdict
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import aliased

from .db import async_session_factory
from .orm import Entity, EntityToEntity, EntityType
from .process_tree import collect_dxf_summary


type PrimitiveCountMap = dict[str, dict[str, int]]

logger = logging.getLogger(__file__)


def count_primitives(primitives: list[dict[str, object]]) -> PrimitiveCountMap:
    counts: defaultdict[str, defaultdict[str, int]] = defaultdict(lambda: defaultdict(int))

    for primitive in primitives:
        block_name = str(primitive.get("block", "")).strip()
        primitive_type = str(primitive.get("type", "")).strip()
        if not block_name or not primitive_type:
            continue
        counts[block_name][primitive_type] += 1

    return {
        block_name: dict(type_counts)
        for block_name, type_counts in counts.items()
    }



def compare_counts(expected: PrimitiveCountMap, actual: PrimitiveCountMap) -> list[str]:
    mismatches: list[str] = []
    for block_name in sorted(set(expected) | set(actual)):
        expected_types = expected.get(block_name, {})
        actual_types = actual.get(block_name, {})
        for primitive_type in sorted(set(expected_types) | set(actual_types)):
            expected_count = expected_types.get(primitive_type, 0)
            actual_count = actual_types.get(primitive_type, 0)
            if expected_count == actual_count:
                continue
            mismatches.append(
                "block={!r} type={} file={} db={}".format(
                    block_name,
                    primitive_type,
                    expected_count,
                    actual_count,
                )
            )
    return mismatches


def compare_layers(expected_layers: set[str], actual_layers: set[str]) -> list[str]:
    mismatches: list[str] = []
    missing_layers = sorted(expected_layers - actual_layers)
    extra_layers = sorted(actual_layers - expected_layers)
    if missing_layers:
        mismatches.append(
            f"Missing layers in the DB: {', '.join(missing_layers)}"
        )
    if extra_layers:
        mismatches.append(
            f"Extra layers in the DB: {', '.join(extra_layers)}"
        )
    return mismatches


def compare_layout_names(expected_layouts: set[str], actual_layouts: set[str]) -> list[str]:
    mismatches: list[str] = []
    missing_layouts = sorted(expected_layouts - actual_layouts)
    extra_layouts = sorted(actual_layouts - expected_layouts)
    if missing_layouts:
        mismatches.append(
            f"Missing layouts in the DB: {', '.join(missing_layouts)}"
        )
    if extra_layouts:
        mismatches.append(
            f"Extra layouts in the DB: {', '.join(extra_layouts)}"
        )
    return mismatches


def _safe_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _collect_expected_layer_names(source_summary: dict[str, Any]) -> set[str]:
    layers_payload = source_summary.get("layers")
    if isinstance(layers_payload, list):
        return {
            str(layer.get("name", "")).strip()
            for layer in layers_payload
            if isinstance(layer, dict) and str(layer.get("name", "")).strip()
        }

    collected: set[str] = set()
    layouts_payload = source_summary.get("layouts")
    if not isinstance(layouts_payload, list):
        return collected

    for layout in layouts_payload:
        if not isinstance(layout, dict):
            continue
        layout_layers = layout.get("layers")
        if not isinstance(layout_layers, list):
            continue
        collected.update(
            str(layer_name).strip()
            for layer_name in layout_layers
            if str(layer_name).strip()
        )
    return collected


def build_verification_report(
    source_summary: dict[str, Any],
    db_snapshot: dict[str, object],
) -> dict[str, object]:
    """Build the final verification report from a file summary and DB snapshot."""

    file_entity = cast(Entity, db_snapshot["file_entity"])
    layouts = cast(list[Entity], db_snapshot["layouts"])
    layers = cast(list[Entity], db_snapshot["layers"])
    blocks = cast(list[Entity], db_snapshot["blocks"])
    primitives = cast(list[Entity], db_snapshot["primitives"])
    on_layer_links = cast(set[tuple[uuid.UUID, uuid.UUID]], db_snapshot["on_layer_links"])

    expected_layout_names = {
        str(layout.get("name", "")).strip()
        for layout in cast(list[dict[str, object]], source_summary.get("layouts", []))
        if str(layout.get("name", "")).strip()
    }
    actual_layout_names = {
        str(layout.name).strip()
        for layout in layouts
        if str(layout.name).strip()
    }

    expected_layer_names = _collect_expected_layer_names(source_summary)
    actual_layer_names = {
        str(layer.name).strip()
        for layer in layers
        if str(layer.name).strip()
    }

    layout_mismatches = compare_layout_names(expected_layout_names, actual_layout_names)
    layout_mismatches.extend(compare_layers(expected_layer_names, actual_layer_names))

    expected_blocks = {
        str(block.get("name", "")).strip(): _safe_int(block.get("entity_count", 0))
        for block in cast(list[dict[str, object]], source_summary["blocks"])
        if str(block.get("name", "")).strip()
    }
    actual_blocks = {
        block.name: _safe_int((block.data or {}).get("entity_count", 0))
        for block in blocks
    }

    block_mismatches: list[str] = []
    for block_name in sorted(set(expected_blocks) | set(actual_blocks)):
        expected_count = expected_blocks.get(block_name)
        actual_count = actual_blocks.get(block_name)
        if expected_count is None:
            block_mismatches.append(f"Extra block in DB: {block_name!r}")
            continue
        if actual_count is None:
            block_mismatches.append(f"Block missing in DB: {block_name!r}")
            continue
        if expected_count != actual_count:
            block_mismatches.append(
                f"block={block_name!r} entity_count file={expected_count} db={actual_count}"
            )

    expected_primitive_counts = count_primitives(
        cast(list[dict[str, object]], source_summary["primitives"])
    )
    actual_primitive_counts = count_primitives(
        [
            {
                "block": (primitive.data or {}).get("block"),
                "type": primitive.entity_type,
            }
            for primitive in primitives
        ]
    )
    primitive_count_mismatches = compare_counts(
        expected_primitive_counts, 
        actual_primitive_counts
    )

    block_names = {block.name for block in blocks}
    unresolved_inserts: list[str] = []
    for primitive in primitives:
        if primitive.entity_type != "INSERT":
            continue
        primitive_data = primitive.data or {}
        target_block = str(primitive_data.get("target_block", "")).strip()
        if target_block and target_block not in block_names:
            unresolved_inserts.append(target_block)

    layer_by_name = {str(layer.name): layer for layer in layers if str(layer.name).strip()}
    missing_layer_links: list[str] = []
    for primitive in primitives:
        primitive_data = primitive.data or {}
        layer_name = primitive_data.get("layer")
        if not isinstance(layer_name, str):
            continue

        layer_entity = layer_by_name.get(layer_name)
        if layer_entity is None:
            missing_layer_links.append(
                f"primitive={primitive.id} layer={layer_name!r}: missing layer entity"
            )
            continue

        if (primitive.id, layer_entity.id) not in on_layer_links:
            missing_layer_links.append(
                f"primitive={primitive.id} layer={layer_name!r}: missing on_layer link"
            )

    wrong_file_id_entities: list[str] = []
    for entity in [*layouts, *layers, *blocks, *primitives]:
        if entity.file_id == file_entity.id:
            continue
        wrong_file_id_entities.append(
            f"entity={entity.id} type={entity.entity_type} name={entity.name!r} file_id={entity.file_id}"
        )

    ok = not any(
        [
            layout_mismatches,
            block_mismatches,
            primitive_count_mismatches,
            unresolved_inserts,
            missing_layer_links,
            wrong_file_id_entities,
        ]
    )

    return {
        "ok": ok,
        "file_id": str(file_entity.id),
        "layouts": {
            "expected": len(expected_layout_names),
            "actual": len(actual_layout_names),
            "mismatches": layout_mismatches,
        },
        "blocks": {
            "expected": len(expected_blocks),
            "actual": len(actual_blocks),
            "mismatches": block_mismatches,
        },
        "primitive_counts": {
            "expected": sum(sum(counts.values()) for counts in expected_primitive_counts.values()),
            "actual": sum(sum(counts.values()) for counts in actual_primitive_counts.values()),
            "mismatches": primitive_count_mismatches,
        },
        "insert_targets": {
            "unresolved": sorted(set(unresolved_inserts)),
        },
        "layer_links": {
            "missing": missing_layer_links,
        },
        "file_id_check": {
            "invalid": wrong_file_id_entities,
        },
    }


def format_verification_report(report: dict[str, object]) -> str:
    """Format the report as CLI-friendly text."""

    layouts = cast(dict[str, object], report["layouts"])
    blocks = cast(dict[str, object], report["blocks"])
    primitive_counts = cast(dict[str, object], report["primitive_counts"])
    insert_targets = cast(dict[str, object], report["insert_targets"])
    layer_links = cast(dict[str, object], report["layer_links"])
    file_id_check = cast(dict[str, object], report["file_id_check"])

    def _render_list(items: list[str], limit: int = 20) -> list[str]:
        if not items:
            return ["    Mismatches: 0"]
        rendered = [f"    Расхождений: {len(items)}"]
        rendered.extend(f"    {item}" for item in items[:limit])
        if len(items) > limit:
            rendered.append(f"    ... и ещё {len(items) - limit}")
        return rendered

    lines = [f"Проверка file_id={report['file_id']}"]
    lines.append("")
    lines.append("[1] Layout и слои:")
    lines.append(f"    Layout в файле: {layouts['expected']}")
    lines.append(f"    Layout в БД:    {layouts['actual']}")
    lines.extend(_render_list(cast(list[str], layouts["mismatches"])))

    lines.append("")
    lines.append("[2] Блоки:")
    lines.append(f"    Блоков в файле: {blocks['expected']}")
    lines.append(f"    Блоков в БД:    {blocks['actual']}")
    lines.extend(_render_list(cast(list[str], blocks["mismatches"])))

    lines.append("")
    lines.append("[3] Примитивы по block/type:")
    lines.append(f"    Всего в файле: {primitive_counts['expected']}")
    lines.append(f"    Всего в БД:    {primitive_counts['actual']}")
    lines.extend(_render_list(cast(list[str], primitive_counts["mismatches"])))

    lines.append("")
    lines.append("[4] INSERT -> block:")
    lines.extend(_render_list(cast(list[str], insert_targets["unresolved"])))

    lines.append("")
    lines.append("[5] primitive -> layer link:")
    lines.extend(_render_list(cast(list[str], layer_links["missing"])))

    lines.append("")
    lines.append("[6] file_id у потомков файла:")
    lines.extend(_render_list(cast(list[str], file_id_check["invalid"])))

    lines.append("")
    lines.append("ИТОГ: " + ("✓ Всё извлечено корректно" if report["ok"] else "⚠ Есть расхождения, см. выше"))
    return "\n".join(lines)


async def _find_file_entity(path: Path, file_id: str | None) -> Entity | None:
    async with async_session_factory() as session:
        if file_id is not None:
            try:
                file_uuid = uuid.UUID(file_id)
            except ValueError as exc:
                raise ValueError(f"Некорректный file_id: {file_id}") from exc

            entity = await session.get(Entity, file_uuid)
            if entity is None:
                return None
            return entity

        stmt = (
            select(Entity)
            .where(Entity.entity_type.in_([EntityType.file, EntityType.zipped_file]))
            .where(Entity.name == path.name)
            .order_by(Entity.created_at.desc())
        )
        result = await session.execute(stmt)
        for entity in result.scalars().all():
            data = entity.data or {}
            if data.get("source_ref") == str(path):
                return entity
        return None


async def _load_db_snapshot(file_entity: Entity) -> dict[str, object]:
    async with async_session_factory() as session:
        layout_result = await session.execute(
            select(Entity)
            .where(Entity.parent_id == file_entity.id)
            .where(Entity.entity_type == EntityType.layout)
            .order_by(Entity.name.asc())
        )
        layouts = layout_result.scalars().all()

        block_result = await session.execute(
            select(Entity)
            .where(Entity.parent_id == file_entity.id)
            .where(Entity.entity_type == EntityType.block)
            .order_by(Entity.name.asc())
        )
        blocks = block_result.scalars().all()

        block_ids = [block.id for block in blocks]

        if file_entity.id is not None:
            layer_result = await session.execute(
                select(Entity)
                .where(Entity.parent_id == file_entity.id)
                .where(Entity.entity_type == EntityType.layer)
                .order_by(Entity.name.asc())
            )
            layers = layer_result.scalars().all()
        else:
            layers = []

        if block_ids:
            parent_alias = aliased(Entity)
            primitive_result = await session.execute(
                select(Entity)
                .join(parent_alias, Entity.parent_id == parent_alias.id)
                .where(parent_alias.id.in_(block_ids))
                .order_by(Entity.created_at.asc())
            )
            primitives = primitive_result.scalars().all()
        else:
            primitives = []

        if primitives:
            layer_ids = [layer.id for layer in layers]
            link_result = await session.execute(
                select(EntityToEntity.src_id, EntityToEntity.dst_id)
                .join(Entity, Entity.id == EntityToEntity.src_id)
                .where(
                    EntityToEntity.link == "on_layer",
                    Entity.is_primitive.is_(True),
                    EntityToEntity.dst_id.in_(layer_ids),
                )
            )
            on_layer_links = set(link_result.all())
            logger.debug("Загружено %d связей on_layer", len(on_layer_links))
        else:
            on_layer_links = set()

    return {
        "file_entity": file_entity,
        "layouts": layouts,
        "layers": layers,
        "blocks": blocks,
        "primitives": primitives,
        "on_layer_links": on_layer_links,
    }


async def verify_extraction(path: Path, file_id: str | None = None) -> dict[str, object]:
    """Compare a DWG/DXF file with what is stored in the current database."""

    resolved_path = path.expanduser().resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Файл не найден: {resolved_path}")

    source_summary = collect_dxf_summary(resolved_path)
    file_entity = await _find_file_entity(resolved_path, file_id)
    if file_entity is None:
        raise LookupError(f"file-сущность не найдена в БД для {resolved_path}")

    db_snapshot = await _load_db_snapshot(file_entity)
    return build_verification_report(source_summary, db_snapshot)