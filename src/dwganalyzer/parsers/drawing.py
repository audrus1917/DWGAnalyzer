"""Extract stable metadata from an ``ezdxf`` drawing."""

from __future__ import annotations

from ezdxf.document import Drawing
from ezdxf.entities import AttDef, Attrib, DXFEntity, Insert, MText, Text
from ezdxf.layouts import BlockLayout

from ..models import (
    AttributeDefinition,
    AttributeValue,
    BlockSummary,
    DrawingSummary,
    EntitySummary,
    LayerSummary,
    LayoutSummary,
)


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _entity_text(entity: DXFEntity) -> str | None:
    if isinstance(entity, MText):
        return _clean_text(entity.plain_text())
    if isinstance(entity, (Text, Attrib, AttDef)):
        return _clean_text(entity.dxf.get("text", None))
    return None


def _attribute_values(entity: DXFEntity) -> tuple[AttributeValue, ...]:
    if not isinstance(entity, Insert):
        return ()
    return tuple(
        AttributeValue(
            tag=str(attribute.dxf.get("tag", "")),
            value=str(attribute.dxf.get("text", "")),
        )
        for attribute in entity.attribs
    )


def _parse_entity(entity: DXFEntity, layout_name: str) -> EntitySummary:
    entity_type = entity.dxftype()
    layer = entity.dxf.get("layer", None)
    block_name = entity.dxf.get("name", None) if isinstance(entity, Insert) else None
    return EntitySummary(
        entity_type=entity_type,
        layout=layout_name,
        layer=str(layer) if layer is not None else None,
        text=_entity_text(entity),
        block_name=str(block_name) if block_name is not None else None,
        attributes=_attribute_values(entity),
    )


def _parse_layouts(drawing: Drawing) -> tuple[LayoutSummary, ...]:
    return tuple(
        LayoutSummary(
            name=layout.name,
            is_modelspace=layout.is_modelspace,
            tab_order=int(layout.dxf.get("taborder", 0) or 0),
            entity_count=len(layout),
        )
        for layout in drawing.layouts
    )


def _parse_layers(drawing: Drawing) -> tuple[LayerSummary, ...]:
    return tuple(
        LayerSummary(
            name=str(layer.dxf.name),
            color=int(layer.dxf.get("color", 7)),
            linetype=str(layer.dxf.get("linetype", "Continuous")),
            lineweight=int(layer.dxf.get("lineweight", -3)),
            is_on=not layer.is_off(),
            is_frozen=layer.is_frozen(),
            is_locked=layer.is_locked(),
        )
        for layer in drawing.layers
    )


def _parse_attribute_definition(entity: AttDef) -> AttributeDefinition:
    return AttributeDefinition(
        tag=str(entity.dxf.get("tag", "")),
        prompt=str(entity.dxf.get("prompt", "")),
        default=str(entity.dxf.get("text", "")),
    )


def _parse_block(block: BlockLayout) -> BlockSummary:
    entities = tuple(block)
    return BlockSummary(
        name=block.name,
        entity_count=len(entities),
        layers=tuple(
            dict.fromkeys(str(entity.dxf.get("layer", "0")) for entity in entities)
        ),
        nested_blocks=tuple(
            dict.fromkeys(
                str(entity.dxf.name)
                for entity in entities
                if isinstance(entity, Insert)
            )
        ),
        text=tuple(
            text
            for entity in entities
            if isinstance(entity, (Text, MText))
            if not isinstance(entity, AttDef)
            if (text := _entity_text(entity)) is not None
        ),
        attribute_definitions=tuple(
            _parse_attribute_definition(entity)
            for entity in entities
            if isinstance(entity, AttDef)
        ),
    )


def _parse_blocks(drawing: Drawing) -> tuple[BlockSummary, ...]:
    return tuple(
        _parse_block(block)
        for block in drawing.blocks
        if not block.block.is_layout_block
    )


def _parse_entities(drawing: Drawing) -> tuple[EntitySummary, ...]:
    return tuple(
        _parse_entity(entity, layout.name)
        for layout in drawing.layouts
        for entity in layout
    )


def parse_drawing(drawing: Drawing, *, source: str) -> DrawingSummary:
    """Convert a loaded drawing to stable domain data.

    Args:
        drawing: Drawing already loaded by the input layer.
        source: Human-readable file or archive reference.

    Returns:
        Drawing metadata without parser-library objects.
    """

    entities = _parse_entities(drawing)
    return DrawingSummary(
        source=source,
        layouts=_parse_layouts(drawing),
        layers=_parse_layers(drawing),
        blocks=_parse_blocks(drawing),
        entities=entities,
        entity_count=len(entities),
    )


__all__ = ["parse_drawing"]
