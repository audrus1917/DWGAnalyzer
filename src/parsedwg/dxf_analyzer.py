"""Utilities for DXF analysis and data extraction."""

from typing import Any

import logging
import re

from ezdxf.document import Drawing
from ezdxf.math import Matrix44
from ezdxf.tools.text import MTextEditor
from ezdxf.addons.geo import GeoProxy

import shapely.geometry
import shapely.validation

from src.parsedwg.constants import ENTITY_TYPES
from src.parsedwg.schemas import BlockDescription

logger = logging.getLogger(__name__)

# Матрица для проекции 3D примитивов на 2D плоскость (игнорируем Z-координату)
PROJECTION_MATRIX = Matrix44.scale(1, 1, 0)


class DXFAnalyzer:
    """Analyze DXF content and extract structured data."""

    def __init__(self, drawing: Drawing):
        self.drawing = drawing

    @staticmethod
    def is_point_like(value: object) -> bool:
        """Return whether a value looks like a point.

        Args:
            value: Value to inspect.

        Returns:
            True if the value looks like a point.
        """

        if hasattr(value, "x") and hasattr(value, "y"):
            return True

        if isinstance(value, (tuple, list)) and len(value) >= 2:
            try:
                float(value[0])
                float(value[1])
            except (TypeError, ValueError):
                return False
            return True

        return False

    @staticmethod
    def format_point(point: Any | None) -> list[float] | None:
        """Normalize a point-like value into a consistent coordinate list.

        Args:
            point: Point object or tuple-like coordinate value.

        Returns:
            Coordinate list or None.

        Raises:
            ValueError: If point is not point-like and cannot be converted.
        """

        if point is None:
            return None

        x = getattr(point, "x", None)
        y = getattr(point, "y", None)
        z = getattr(point, "z", 0.0)
        if x is not None and y is not None:
            return [x, y, z]

        if isinstance(point, (tuple, list)) and len(point) >= 2:
            try:
                px = float(point[0])
                py = float(point[1])
                pz = float(point[2]) if len(point) >= 3 else 0.0
            except (TypeError, ValueError) as e:
                logger.warning("Failed to convert point: %s", e)
                raise

            return [px, py, pz]
        raise ValueError(f"Value is not point-like: {point}")

    @staticmethod
    def get_text(entity) -> str:
        """Extract text from TEXT or MTEXT entities when present.

        Args:
            entity: DXF entity.

        Returns:
            Entity text or an empty string.
        """

        entity_type = entity.dxftype()
        if entity_type == "TEXT":
            return entity.dxf.text.rstrip()
        elif entity_type == "MTEXT":
            plain_text = getattr(entity, "plain_text", None)
            if callable(plain_text):
                return str(plain_text()).rstrip()
        return ""

    @classmethod
    def get_virtual_entities(cls, entity):
        """Recursively collect virtual entities for an INSERT.

        Args:
            entity: DXF entity that may expose virtual_entities.

        Returns:
            List of virtual child entities.
        """
        children = []
        for ch in entity.virtual_entities():
            if ch.dxftype() == "INSERT":
                ch_data = cls.get_virtual_entities(ch)
                if ch_data is not None:
                    children += ch_data
            else:
                children.append(ch)
        return children


    @classmethod
    def get_entity_data(
        cls,
        entity,
        parent,
        layout: Any | None = None,
        is_virtual: bool = False
    ) -> dict[str, Any] | None:
        """Return structured data for a DXF entity.

        Args:
            entity: DXF entity.
            parent: Parent layout or block.
            layout: Layout that contains the entity.

        Returns:
            Entity payload, or None for an unsupported type.
        """

        dxftype = entity.dxftype()
        if dxftype not in ENTITY_TYPES:
            logger.warning("Unknown entity type: %s. It will be treated as PRIMITIVE.", dxftype)
            return None

        if dxftype in [
            "POINT", "LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", 
            "SPLINE", "SOLID", "HATCH"
        ]:
            try:
                entity.transform(PROJECTION_MATRIX)
            except (AttributeError, TypeError):
                # Пропускаем объекты, которые не поддерживают трансформацию матрицей
                pass
            except Exception as e:
                logger.warning("Failed to apply projection to entity: %s", e, exc_info=True)


        entity_data = {
            "type": ENTITY_TYPES[dxftype],
            "parent": parent,
            "layer": entity.dxf.layer if hasattr(entity.dxf, "layer") else None,
            "layout": layout,
            "is_virtual": is_virtual
        }

        # Attach textual content when present.
        if text_value := cls.get_text(entity):
            entity_data["description"] = re.sub(r"\s+", " ", text_value).strip()

        # Preserve raw DXF attributes in a normalized form.
        dxf_attribs: dict[str, Any] = {}
        for attr_name, value in entity.dxf.all_existing_dxf_attribs().items():
            if cls.is_point_like(value):
                dxf_attribs[attr_name] = cls.format_point(value)
            else:
                dxf_attribs[attr_name] = value

        if dxf_attribs:
            entity_data["dxf_attribs"] = dxf_attribs

        if dxftype in [
            "POINT", "LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", 
            "SPLINE", "SOLID", "HATCH"
        ]:
            proxy = GeoProxy.from_dxf_entities(entity)
            shapely_geom = shapely.geometry.shape(proxy.__geo_interface__)
            if not shapely_geom.is_valid:
                shapely_geom = shapely.validation.make_valid(shapely_geom)

            entity_data["area"] = shapely_geom.area
            entity_data["length"] = shapely_geom.length
            entity_data["geom"] = shapely_geom.wkt

        match dxftype:
            case "INSERT":
                entity_data["target_block"] = entity.dxf.name
                entity_data["attribs"] = {
                    attr.dxf.tag: cls.format_point(attr.dxf.text)
                    if cls.is_point_like(attr.dxf.text) else attr.dxf.text
                    for attr in entity.attribs
                }

                children = cls.get_virtual_entities(entity)
                if children:
                    entity_data["children"] = [
                        cls.get_entity_data(
                            ch,
                            parent=entity,
                            layout=layout,
                            is_virtual=True
                        ) for ch in children
                    ]

            case "TEXT" | "MTEXT":
                entity_data["geom"] = "POINT({} {})".format(
                    entity.dxf.insert.x, entity.dxf.insert.y
                )

            case "MULTILEADER":
                # Annotation leader segments.
                line_segments = []
                for c_entity in entity.virtual_entities():
                    if c_entity.dxftype() == 'LINE':
                        start = c_entity.dxf.start
                        end = c_entity.dxf.end
                        line_segments.append(f"({start.x} {start.y}, {end.x} {end.y})")
                    elif c_entity.dxftype() == 'POLYLINE':
                        points = [vertex.dxf.location.xyz for vertex in c_entity.vertices]
                        for i in range(len(points) - 1):
                            start = points[i]
                            end = points[i + 1]
                            line_segments.append(f"({start[0]} {start[1]}, {end[0]} {end[1]})")
                    elif c_entity.dxftype() == 'LWPOLYLINE':
                        points = c_entity.get_points("xy")
                        for i in range(len(points) - 1):
                            start = points[i]
                            end = points[i + 1]
                            line_segments.append(f"({start[0]} {start[1]}, {end[0]} {end[1]})")

                entity_text = entity.get_mtext_content() if hasattr(entity, "get_mtext_content") else ""
                if entity_text:
                    clean_text = MTextEditor(entity_text).text
                    entity_data["description"] = re.sub(r"\s+", " ", clean_text).strip()

                # Build WKT for the MultiLineString.
                multiline_wkt = f"MULTILINESTRING({', '.join(line_segments)})"
                entity_data["geom"] = f"{multiline_wkt}"

        return entity_data

    @classmethod
    def analyze_block(
        cls,
        doc: Drawing,
        block_name,
        block_data=None,
        processed=None
    ):
        """Recursively analyze a block definition to extract layers, nested blocks, and text."""
        if block_data is None:
            block_data = BlockDescription()

        if processed is None:
            processed = set()

        if block_name in processed:
            return block_data
        processed.add(block_name)

        block_def = doc.blocks.get(block_name)
        if not block_def:
            return block_data

        for entity in block_def:
            # 1. Layers.
            block_data.primitives_layers.add(entity.dxf.layer)

            # 2. Text content (TEXT and MTEXT).
            val = None
            if entity.dxftype() == 'TEXT':
                val = entity.dxf.text.strip()
            elif entity.dxftype() == 'MTEXT':
                plain_text = getattr(entity, "plain_text", None)
                if callable(plain_text):
                    val = str(plain_text()).rstrip()
                if val:
                    block_data.text_content.add(val)

            # 3. ATTDEFS (attribute definitions).
            if entity.dxftype() == 'ATTDEF':
                block_data.attdefs.append({
                    "tag": entity.dxf.tag,
                    "prompt": getattr(entity.dxf, 'prompt', ''), # User-facing prompt.
                    "default": entity.dxf.text # Default value.
                })

            # 4. Recurse into nested inserts.
            if entity.dxftype() == 'INSERT':
                nested_name = entity.dxf.name
                block_data.nested_blocks.add(nested_name)
                cls.analyze_block(doc, nested_name, block_data, processed)

        return block_data

    @classmethod
    def get_short_block_description(
        cls,
        doc: Drawing,
        block_name: str
    ) -> BlockDescription:
        """Return a DXF block description.

        Args:
            doc: Loaded ezdxf drawing.
            block_name: Block name.

        Returns:
            Summary description of the block.

        Raises:
            ValueError: If block_name is not found in the file.
        """

        msp = doc.modelspace()
        block = doc.blocks.get(block_name)
        if block is None:
            logger.error("Block '%s' not found in the file.", block_name)
            raise ValueError(f"Block '{block_name}' not found in the file.")

        block_info: BlockDescription = cls.analyze_block(doc, block_name)
        block_info.block_name = block_name

        inserts = msp.query(f'INSERT[name=="{block.name}"]')
        insert_samples = []
        insert_layers = []
        idx = 0
        for entity in inserts:
            if entity.dxf.layer:
                insert_layers.append(entity.dxf.layer)
            if entity.attribs and idx < 3:  # Capture sample attributes from up to 3 inserts.
                sample_attribs = {}
                for attr in entity.attribs:
                    sample_attribs[attr.dxf.tag] = attr.dxf.text
                insert_samples.append(sample_attribs)
                idx += 1

        if insert_samples:
            block_info.insert_samples = insert_samples
        return block_info
