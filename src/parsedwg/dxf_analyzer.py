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
from src.parsedwg.utils.geom import is_point_like, format_point

logger = logging.getLogger(__name__)

# Матрица для проекции 3D примитивов на 2D плоскость (игнорируем Z-координату)
PROJECTION_MATRIX = Matrix44.scale(1, 1, 0)


class DrawingAnalyzer:
    """Analyze DXF content and extract structured data."""

    def __init__(self, drawing: Drawing):
        self.drawing = drawing

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

    @staticmethod
    def get_shapely_geometry(entity: Any) -> shapely.geometry.base.BaseGeometry | None: 
        """Convert a DXF entity into a shapely geometry when possible."""

        dxftype = entity.dxftype()
        if dxftype in ("TEXT", "MTEXT"):
            return shapely.geometry.Point(entity.dxf.insert.x, entity.dxf.insert.y)
        
        try:
            proxy = GeoProxy.from_dxf_entities(entity)
        except (AttributeError, TypeError, ValueError):
            return None

        shapely_geom = shapely.geometry.shape(dict(proxy.__geo_interface__))
        if not shapely_geom.is_valid:
            shapely_geom = shapely.validation.make_valid(shapely_geom)
        return shapely_geom

    @classmethod
    def get_multileader_geometry(cls, entity):
        """Build a shapely MultiLineString from MULTILEADER virtual entities."""

        line_parts: list[list[tuple[float, float]]] = []

        for child in entity.virtual_entities():
            child_geom = cls.get_shapely_geometry(child)
            if child_geom is None:
                continue

            if isinstance(child_geom, shapely.geometry.LineString):
                line_parts.append([
                    (float(point[0]), float(point[1])) for point in child_geom.coords
                ])
            elif isinstance(child_geom, shapely.geometry.MultiLineString):
                line_parts.extend([
                    [(float(point[0]), float(point[1])) for point in line.coords]
                    for line in child_geom.geoms
                ])
            elif isinstance(child_geom, shapely.geometry.Polygon):
                line_parts.append([
                    (float(point[0]), float(point[1]))
                    for point in child_geom.exterior.coords
                ])
                line_parts.extend([
                    [(float(point[0]), float(point[1])) for point in ring.coords]
                    for ring in child_geom.interiors
                ])

        if not line_parts:
            return None
        return shapely.geometry.MultiLineString(line_parts)

    @classmethod
    def get_entity_points(cls, entity) -> list[list[float]]:
        """Extract normalized vertex lists for entities that expose point sequences."""

        dxftype = entity.dxftype()
        if dxftype == "LWPOLYLINE":
            get_points = getattr(entity, "get_points", None)
            if callable(get_points):
                return [format_point(point) for point in get_points("xy")]

        if dxftype == "POLYLINE":
            get_points = getattr(entity, "points", None)
            if callable(get_points):
                return [format_point(point) for point in get_points()]

        if dxftype == "SOLID":
            points: list[list[float]] = []
            for attr_name in ("vtx0", "vtx1", "vtx2", "vtx3"):
                if entity.dxf.hasattr(attr_name):
                    points.append(format_point(getattr(entity.dxf, attr_name)))
            return points

        return []


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
            if is_point_like(value):
                dxf_attribs[attr_name] = format_point(value)
            else:
                dxf_attribs[attr_name] = value

        if dxf_attribs:
            entity_data["dxf_attribs"] = dxf_attribs

        if points := cls.get_entity_points(entity):
            entity_data["points"] = points

        if dxftype in [
            "POINT", "LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", 
            "SPLINE", "SOLID", "HATCH"
        ]:
            shapely_geom = cls.get_shapely_geometry(entity)

            if shapely_geom is not None:
                entity_data["area"] = shapely_geom.area
                entity_data["length"] = shapely_geom.length
                entity_data["geom"] = shapely_geom.wkt

        match dxftype:
            case "INSERT":
                entity_data["target_block"] = entity.dxf.name
                entity_data["attribs"] = {
                    attr.dxf.tag: format_point(attr.dxf.text)
                    if is_point_like(attr.dxf.text) else attr.dxf.text
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
                if shapely_geom := cls.get_shapely_geometry(entity):
                    entity_data["geom"] = shapely_geom.wkt
            case "HATCH":
                entity_data["name"] = entity.dxf.pattern_name

            case "MULTILEADER":
                entity_text = entity.get_mtext_content() if hasattr(entity, "get_mtext_content") else ""
                if entity_text:
                    clean_text = MTextEditor(entity_text).text
                    entity_data["description"] = re.sub(r"\s+", " ", clean_text).strip()

                if shapely_geom := cls.get_multileader_geometry(entity):
                    entity_data["geom"] = shapely_geom.wkt

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
            block_data = {}

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
            block_data.setdefault("primitives_layers", set()).add(entity.dxf.layer)

            # 2. Text content (TEXT and MTEXT).
            val = None
            if entity.dxftype() == 'TEXT':
                val = entity.dxf.text.strip()
            elif entity.dxftype() == 'MTEXT':
                plain_text = getattr(entity, "plain_text", None)
                if callable(plain_text):
                    val = str(plain_text()).rstrip()
                if val:
                    block_data.setdefault("text_content", set()).add(val)

            # 3. ATTDEFS (attribute definitions).
            if entity.dxftype() == 'ATTDEF':
                block_data.setdefault("attdefs", []).append({
                    "tag": entity.dxf.tag,
                    "prompt": getattr(entity.dxf, 'prompt', ''), # User-facing prompt.
                    "default": entity.dxf.text # Default value.
                })

            # 4. Recurse into nested inserts.
            if entity.dxftype() == 'INSERT':
                nested_name = entity.dxf.name
                block_data.setdefault("nested_blocks", set()).add(nested_name)
                cls.analyze_block(doc, nested_name, block_data, processed)

        return block_data

    @classmethod
    def build_block_data(
        cls,
        doc: Drawing,
        entity: Any
    ) -> Any:
        """Return a DXF block description.

        Args:
            doc: Loaded ezdxf drawing.
            entity: DXF entity.

        Returns:
            Summary description of the block.

        Raises:
            ValueError: If block_name is not found in the file.
        """

        msp = doc.modelspace()
        block_name = entity.dxf.name
        block = doc.blocks.get(block_name)
        if block is None:
            logger.error("Block '%s' not found in the file.", block_name)
            raise ValueError(f"Block '{block_name}' not found in the file.")

        block_info = cls.analyze_block(doc, block_name)
        block_info["block_name"] = block_name

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
            block_info["insert_samples"] = insert_samples
        return block_info
