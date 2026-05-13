"""Utilities for DXF analysis and data extraction."""

from typing import Any
import sys
import logging
import re

from ezdxf import entities as dfx_entities
from ezdxf.document import Drawing
from ezdxf import path
from ezdxf.math import area as math_area
from ezdxf.tools.text import MTextEditor
from ezdxf.addons.geo import GeoProxy
import ezdxf_shapely

from .constants import ENTITY_TYPES

logger = logging.getLogger(__name__)


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

            case "LWPOLYLINE":
                logger.debug("`LWPOLYLINE` case: %s", entity)
                logger.debug("LWPOLYLINE is closed? %s", entity.is_closed)
                points = entity.get_points("xy")
                logger.debug("Points: %s", points)
                wkt_geom = None
                try:
                    wkt_geom = ezdxf_shapely.convert_lwpolyline(entity)
                except Exception as e:
                    logger.error("Error converting LWPOLYLINE: %s", e)
                    dxf_geom = GeoProxy.from_dxf_entities(entity)
                    print(dxf_geom)
                    # shapely_geom = dxf_geom.geometry[0]
                    # wkt_geom = shapely_geom.wkt

                    # shapely_geom = proxy.geometry # Requires shapely
                    # wkt_geom = shapely_geom.wkt
                    # logger.debug(f"Closed 2-point LWPOLYLINE WKT: {wkt_geom}")

                if wkt_geom is not None:
                    entity_data["geom"] = wkt_geom
                    logger.debug("LWPOLYLINE GEOM: %s", wkt_geom)

            case "POLYLINE":
                logger.debug("POLYLINE is closed? %s", entity.is_closed)
                logger.debug("Is instance of dfx_entities.Polyline? %s", isinstance(entity, dfx_entities.Polyline))
                # geom = ezdxf_shapely.convert_(entity)
                # if geom is not None:
                #     entity_data["geom"] = geom.wkt
                #     logger.debug("POLYLINE GEOM: %s", geom.wkt)
            # case "LINE":
            #     geom = ezdxf_shapely.convert_line(entity)
            #     if geom is not None:
            #         entity_data["geom"] = geom.wkt
            #         logger.debug("LINE GEOM: %s", geom.wkt)
            case "CIRCLE":
                entity_data["center"] = cls.format_point(entity.dxf.center)
                entity_data["radius"] = entity.dxf.radius
                entity_data["geom"] = "POINT({} {})".format(
                    entity.dxf.center.x, entity.dxf.center.y
                )
            case "ARC":
                entity_data["center"] = cls.format_point(entity.dxf.center)
                entity_data["radius"] = entity.dxf.radius
                entity_data["start_angle"] = entity.dxf.start_angle
                entity_data["end_angle"] = entity.dxf.end_angle
                entity_data["geom"] = "POINT({} {})".format(
                    entity.dxf.center.x, entity.dxf.center.y
                )
            case "ELLIPSE":
                entity_data["center"] = cls.format_point(entity.dxf.center)
                entity_data["major_axis"] = cls.format_point(entity.dxf.major_axis)
                entity_data["ratio"] = entity.dxf.ratio
                entity_data["start_param"] = entity.dxf.start_param
                entity_data["end_param"] = entity.dxf.end_param
                entity_data["geom"] = "POINT({} {})".format(
                    entity.dxf.center.x, entity.dxf.center.y
                )
            case "TEXT" | "MTEXT":
                entity_data["geom"] = "POINT({} {})".format(
                    entity.dxf.insert.x, entity.dxf.insert.y
                )
            case "HATCH":
                try:
                    entity_data["name"] = entity.dxf.pattern_name
                    hatch_path = path.make_path(entity)
                    vertices = list(hatch_path.flattening(distance=0.01))

                    # Build the coordinate list for WKT.
                    coords = ", ".join([f"{p.x} {p.y}" for p in vertices])

                    # Close the polygon if the first and last vertices differ.
                    if vertices[0] != vertices[-1]:
                        coords += f", {vertices[0].x} {vertices[0].y}"

                    total_length = sum(p1.distance(p2) for p1, p2 in zip(vertices, vertices[1:]))
                    entity_data["data"] = {}
                    entity_data["data"]["length"] = total_length
                    entity_data["geom"] = f"POLYGON(({coords}))"
                    entity_data["data"]["area"] = math_area(vertices)
                except TypeError as e:
                    logger.warning("Failed to process HATCH entity: %s", e)
                except Exception as e:
                    logger.error("Error while processing HATCH entity: %s", e)

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
        data=None,
        processed=None
    ):
        if data is None:
            data = {
                "primitives_layers": set(),
                "nested_blocks": set(),
                "text_content": set(),
                "attdefs": []  # List of attribute definitions.
            }
        if processed is None:
            processed = set()

        if block_name in processed:
            return data
        processed.add(block_name)

        block_def = doc.blocks.get(block_name)
        if not block_def:
            return data

        for entity in block_def:
            # 1. Layers.
            data["primitives_layers"].add(entity.dxf.layer)

            # 2. Text content (TEXT and MTEXT).
            val = None
            if entity.dxftype() == 'TEXT':
                val = entity.dxf.text.strip()
            elif entity.dxftype() == 'MTEXT':
                plain_text = getattr(entity, "plain_text", None)
                if callable(plain_text):
                    val = str(plain_text()).rstrip()
                if val:
                    data["text_content"].add(val)

            # 3. ATTDEFS (attribute definitions).
            if entity.dxftype() == 'ATTDEF':
                data["attdefs"].append({
                    "tag": entity.dxf.tag,
                    "prompt": getattr(entity.dxf, 'prompt', ''), # User-facing prompt.
                    "default": entity.dxf.text # Default value.
                })

            # 4. Recurse into nested inserts.
            if entity.dxftype() == 'INSERT':
                nested_name = entity.dxf.name
                data["nested_blocks"].add(nested_name)
                cls.analyze_block(doc, nested_name, data, processed)

        return data

    @classmethod
    def get_block_decsription(
        cls,
        doc: Drawing,
        block_name: str
    ) -> dict[str, Any]:
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

        internal = cls.analyze_block(doc, block_name)
        block_info = {
            "block_name": block_name
        }

        if primitives_layers := list(internal["primitives_layers"]):
            block_info["primitives_layers"] = primitives_layers
        if nested_blocks := list(internal["nested_blocks"]):
            block_info["nested_blocks"] = nested_blocks
        if text_content := list(internal["text_content"]):
            block_info["text_content"] = text_content
        if attdefs := internal["attdefs"]:
            block_info["attdefs"] = attdefs

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
