"""Walk DWG/DXF sources and save the entity tree to the database."""

from __future__ import annotations

from typing import Any, Generator, Protocol, cast

import sys
import logging
import tempfile
import zipfile

from pathlib import Path

from ezdxf.document import Drawing
from sqlalchemy import func, select, exc as sa_exc

from src.parsedwg import errors
from src.parsedwg.settings import settings
from src.parsedwg.constants import ENTITY_TYPES, EntityType
from src.parsedwg.db import session_factory
from src.parsedwg.orm import Entity, EntityEmbedding, Project, EntityToEntity
from src.parsedwg.dxf_analyzer import DrawingAnalyzer
from src.parsedwg.utils import safe_float, extract_from_zip, read_drawing, file_md5
from src.parsedwg.table_analysis import TextClusterAnalyzer
from src.parsedwg.schemas import DrawingSource

logger = logging.getLogger(__name__)

PRIMITIVE_BATCH_SIZE = 1000
DETAIL_LEVELS = ("low", "medium", "high")
DEFAULT_DETAIL_LEVEL = "high"
ENTITY_TYPE_ALIASES = {
    "MULTILEADER": "MLEADER",
}


def _entity_type_name(value: object) -> str | None:
    if isinstance(value, EntityType):
        return value.name
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, int):
        try:
            return EntityType(value).name
        except ValueError:
            return None
    return None


def _extract_primitive_location(primitive_payload: dict[str, object]) -> object | None:
    dxf_attribs = primitive_payload.get("dxf_attribs")
    if isinstance(dxf_attribs, dict):
        for key in ("insert", "center", "start", "location"):
            value = dxf_attribs.get(key)
            if value not in (None, "", [], {}):
                return value

    for key in ("center", "start", "location"):
        value = primitive_payload.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def get_block_payload(block: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    block_data: dict[str, Any] = {
        "entity_count": int(block.get("entity_count", 0) or 0),
    }

    if bool(block.get("is_table")) and isinstance(block.get("table"), dict):
        block_data["table"] = block["table"]

    description = block.get("description")
    if not isinstance(description, dict):
        return str(description or ""), block_data

    for key in ("primitives_layers", "nested_blocks"):
        value = description.get(key)
        if value not in (None, "", [], {}):
            block_data[key] = value

    for key in ("text_content", "attdefs", "insert_samples"):
        value = description.get(key)
        if value not in (None, "", [], {}):
            block_data[key] = value

    compact_description = {
        key: block_data[key]
        for key in ("primitives_layers", "nested_blocks")
        if key in block_data
    }
    return str(compact_description), block_data


def get_primitive_payload(
    primitive_payload: dict[str, object],
    detail_level: str,
    block_name: str | None,
    layout_name: str | None,
    description: object,
    geometry: object,
) -> dict[str, object]:
    """Build a primitive entity payload with variable detail level."""

    data: dict[str, object] = {}

    if block_name:
        data["block"] = block_name

    type_name = _entity_type_name(primitive_payload.get("type"))
    if type_name:
        data["type"] = type_name

    if isinstance(description, str) and description.strip():
        data["text"] = description.strip()

    layer_name = primitive_payload.get("layer")
    if isinstance(layer_name, str) and layer_name.strip():
        data["layer"] = layer_name

    location = _extract_primitive_location(primitive_payload)
    if location is not None:
        data["location"] = location

    if layout_name:
        data["layout"] = layout_name
    if geometry not in (None, "", [], {}):
        data["geom"] = geometry
    for key in (
        "target_block",
        "center",
        "radius",
        "start_angle",
        "end_angle",
        "major_axis",
        "ratio",
        "start_param",
        "end_param",
    ):
        value = primitive_payload.get(key)
        if value not in (None, "", [], {}):
            data[key] = value

    nested_data = primitive_payload.get("data")
    if isinstance(nested_data, dict) and nested_data:
        data.update(nested_data)

    for key in ("dxf_attribs", "attribs", "name"):
        value = primitive_payload.get(key)
        if value not in (None, "", [], {}):
            data[key] = value
    if primitive_payload.get("is_virtual"):
        data["is_virtual"] = True

    return data


class DrawingProcessor:
    """Walk a source tree and build DWG/DXF processing jobs."""

    def __init__(self, source_path: Path, root_path: Path | None = None):
        """Initialize the DWG/DXF source processor.

        Args:
            source_path: Source path to process.
            root_path: Root path used for relative links and traversal.

        Returns:
            None.

        Raises:
            FileNotFoundError: If root_path does not exist.
        """
        self.source_path = source_path
        self.root_path = root_path or source_path
        if not self.root_path.exists():
            raise FileNotFoundError(f"Path {self.root_path} was not found.")

    def walk(self, sources_path: Path) -> Generator[DrawingSource, None, None]:
        """Walk a directory and yield DWG/DXF parsing jobs.

        Args:
            sources_path: Directory to scan for DWG/DXF/DXB files and ZIP archives.

        Yields:
            File descriptors and ZIP member descriptors for subsequent processing.
        """

        for file_path in sorted(path for path in sources_path.rglob("*") if path.is_file()):
            suffix = file_path.suffix.lower()
            if suffix in {".dwg", ".dxf", ".dxb"}:
                parent_rel = file_path.parent.relative_to(sources_path)
                parent_rel_str = "" if str(parent_rel) == "." else parent_rel.as_posix()
                yield DrawingSource(
                    kind="file",
                    root=str(sources_path),
                    source=str(file_path),
                    name=file_path.name,
                    file_type=suffix,
                    parent_rel=parent_rel_str,
                )
                continue

            if suffix != ".zip":
                continue

            zip_parent_rel = file_path.parent.relative_to(sources_path)
            zip_parent_rel_str = "" if str(zip_parent_rel) == "." else zip_parent_rel.as_posix()
            try:
                with zipfile.ZipFile(file_path) as archive:
                    for member_name in sorted(info.filename for info in archive.infolist()):
                        if member_name.endswith("/"):
                            continue
                        member_suffix = Path(member_name).suffix.lower()
                        if member_suffix not in {".dwg", ".dxf", ".dxb"}:
                            continue
                        yield DrawingSource(
                            kind="zipped_file",
                            root=str(sources_path),
                            source=str(file_path),
                            member=member_name,
                            name=Path(member_name).name,
                            file_type=member_suffix,
                            zip_parent_rel=zip_parent_rel_str,
                            parent_rel=zip_parent_rel_str,
                        )
            except zipfile.BadZipFile:
                logger.warning("Skipping corrupted ZIP archive: %s", file_path)


def build_entity_embedding(text_value: str | None) -> EntityEmbedding | None:
    """Build an entity embedding from text content, if available."""

    if settings.use_ts:
        if text_value is None or not text_value.strip():
            return None
        entity_text = func.to_tsvector("russian", text_value)
        if entity_text:
            return EntityEmbedding(entity_text=entity_text)


def coerce_entity_type(value: object) -> EntityType:
    """Coerce a value into an EntityType, with some normalization and fallbacks."""

    if isinstance(value, EntityType):
        return value
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized:
            normalized = ENTITY_TYPE_ALIASES.get(normalized, normalized)
            return ENTITY_TYPES.get(normalized, EntityType.PRIMITIVE)
    if isinstance(value, int):
        try:
            return EntityType(value)
        except ValueError:
            return EntityType.PRIMITIVE
    return EntityType.PRIMITIVE


def collect_entity_layers(doc, entity, seen_blocks: set[str] | None = None) -> set[str]:
    layers: set[str] = set()
    layer_name = getattr(entity.dxf, "layer", "")
    if layer_name:
        layers.add(str(layer_name))

    if entity.dxftype() != "INSERT" or not entity.dxf.hasattr("name"):
        return layers

    block_name = str(entity.dxf.name)
    if seen_blocks is None:
        seen_blocks = set()
    if block_name in seen_blocks:
        return layers

    block = doc.blocks.get(block_name)
    if block is None:
        return layers

    nested_seen = {*seen_blocks, block_name}
    for nested_entity in block:
        layers.update(collect_entity_layers(doc, nested_entity, nested_seen))
    return layers


def _is_layout_block(block) -> bool:
    block_name = block.name.lower()
    return block_name.startswith("*model_space") or block_name.startswith("*paper_space")


def collect_layout_entities(doc) -> Generator[dict[str, Any] | None, None, None]:
    """Iterate over all layout entities and return their payloads.

    Args:
            doc: Loaded ezdxf drawing.

    Yields:
            Layout entity payloads, or None for unsupported DXF types.
    """

    for layout in doc.layouts:
        logger.debug("Processing layout: %s, entity count: %d", layout.name, len(layout))
        for dxf_entity in layout:
            yield DrawingAnalyzer.get_entity_data(
                dxf_entity, 
                parent=layout,
                layout=layout
            )


def collect_drawing_summary(drawing: Drawing) -> dict[str, Any]:
    """Collect layout, block, and primitive data from a drawing.

    Args:
        drawing: Loaded ezdxf drawing.

    Returns:
        Summary with layouts, layers, blocks, primitives, and their links.
    """

    # Preliminary statistics for diagnostics.
    logger.debug("Layout count: %d", len(drawing.layouts))
    logger.debug("Block count: %d", len(drawing.blocks))
    logger.debug("Layer count: %d", len(drawing.layers))
    total_primitives: int = 0
    for layout in drawing.layouts:
        total_primitives += len(layout)
    logger.debug("Primitive count across layouts: %d", total_primitives)

    layouts: list[dict[str, object]] = []
    for layout in drawing.layouts:
        layouts.append({
            "name": layout.name,
            "data": {
                "ms": layout.is_modelspace,
                "tab": safe_float(layout.dxf.get("taborder", None)),
            }
        })

    layers: list[dict[str, Any]] = []
    for layer in drawing.layers:
        name = str(layer.dxf.name)
        layers.append({
            "name": name,
            "data": {
                "color": safe_float(layer.dxf.get("color", None)),
                "lt": str(layer.dxf.get("linetype", "")) or None,
                "lw": safe_float(layer.dxf.get("lineweight", None)),
                "on": not layer.is_off(),
                "frozen": layer.is_frozen(),
                "locked": layer.is_locked(),
            }
        })

    blocks: list[dict[str, object]] = []
    block_links = {}
    block_layers = {}    
    for block in drawing.blocks:
        if _is_layout_block(block):
            continue
        block_data = DrawingAnalyzer.build_block_data(drawing, block)
        table_stats = TextClusterAnalyzer.analyze_table(block)
        blocks_def = {
            "name": block.name,
            "entity_count": sum(1 for _ in block),
            # "description": block_description or '',
            "is_table": table_stats.is_table,
        }
        if table_stats.is_table:
            blocks_def["table"] = {
                "title": table_stats.title,
                "rows": table_stats.rows,
                "total_texts": table_stats.total_texts,
                "table_like_texts": table_stats.table_like_texts,
                "x_clusters": len(table_stats.x_clusters),
                "y_clusters": len(table_stats.y_clusters),
            }
        blocks.append(blocks_def)

        if block_data and block_data.get("primitives_layers"):
            block_layers[block.name] = block_data["primitives_layers"]

        for entity in block:
            if entity.dxftype() == "INSERT":
                block_links.setdefault(block.name, set()).add(entity.dxf.name)

    primitives: list[dict[str, object]] = []
    for entity_data in collect_layout_entities(drawing):
        if entity_data is not None:
            primitives.append(entity_data)

    primitives_payload = cast(list[dict[str, object]], primitives)

    return {
        "layouts": layouts,
        "layers": layers,
        "blocks": blocks,
        "primitives": primitives_payload,
        "block_links": block_links,
        "block_layers": block_layers,
    }


def process_entry(entry: DrawingSource) -> DrawingSource:
    """Process a single job entry and return its summary.

    Args:
        entry: File descriptor or ZIP member descriptor to process.

    Returns:
        Summary payload with source_ref, entity_md5, and summary.

    Raises:
        ValueError: If a ZIP entry does not specify member.
    """
    source = Path(entry.source)

    with tempfile.TemporaryDirectory(prefix="parsedwg-process-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)

        is_zip = ""
        if entry.kind == "file":
            source_ref = entry.source
            working_path = source
            entity_md5 = file_md5(working_path)
        else:
            is_zip = " (zip)"
            member_name = entry.member
            if member_name is None:
                raise ValueError("Missing member for zipped_file entry.")

            working_path = extract_from_zip(source, member_name, temp_dir)
            source_ref = f"{entry.source}::{member_name}"
            entity_md5 = file_md5(working_path)

        logger.info("Processing file: %s%s", source_ref, is_zip)
        entry.entity_md5 = entity_md5
        drawing = read_drawing(working_path)
        entry.summary = collect_drawing_summary(drawing)

    return entry


def create_folders_tree(
    session,
    root_path: Path,
    project_id,
) -> tuple[dict[str, Entity], int]:
    root_entity = Entity(
        name=root_path.name or str(root_path),
        description=f"Scan source: {root_path}",
        entity_type=EntityType.FOLDER,
        data={"path": str(root_path)},
        project_id=project_id,
        embedding_data=build_entity_embedding(f"Scan source: {root_path}"),
    )
    session.add(root_entity)
    session.flush()

    folders: dict[str, Entity] = {"": root_entity}
    created = 1

    for dir_path in sorted(p for p in root_path.rglob("*") if p.is_dir()):
        rel = dir_path.relative_to(root_path).as_posix()
        parent_rel = "" if dir_path.parent == root_path else dir_path.parent.relative_to(root_path).as_posix()
        parent_entity = folders[parent_rel]

        folder_entity = Entity(
            parent_id=parent_entity.id,
            project_id=project_id,
            name=dir_path.name,
            description=f"Directory: {dir_path}",
            entity_type=EntityType.FOLDER,
            data={"path": str(dir_path)},
            embedding_data=build_entity_embedding(f"Directory: {dir_path}"),
        )
        session.add(folder_entity)
        session.flush()
        folders[rel] = folder_entity
        created += 1

    return folders, created


def flush_primitives_batch(
    session,
    primitive_batch: list[Entity],
    primitive_layer_links: list[tuple[Entity, Entity]],
    processed_count: int,
    primitives_total: int,
    final: bool = False,
) -> int:
    if not primitive_batch:
        return 0

    if final:
        logger.info(
            "Saving final primitive batch: %d / %d",
            processed_count,
            primitives_total,
        )
    else:
        logger.info(
            "Saving primitive batch: %d / %d",
            processed_count,
            primitives_total,
        )

    session.add_all(primitive_batch)
    try:
        session.flush()
    except sa_exc.SQLAlchemyError as exc:
        logger.error("Error flushing primitive batch: %s", exc)
        for x in primitive_batch:
            logger.error(f"Failed primitive: {x.entity_type} - {x.geom}")

        session.rollback()

        # FIXME: temporary solution to skip problematic batches, should be
        # improved with better error handling and data validation
        sys.exit(1)

        return 0

    for primitive_entity, layer_entity in primitive_layer_links:
        session.add(
            EntityToEntity(
                dst_id=layer_entity.id,
                src_id=primitive_entity.id,
                link="on_layer",
            )
        )

    created_count = len(primitive_batch)
    session.commit()
    primitive_batch.clear()
    primitive_layer_links.clear()
    return created_count


def save_to_db(
    sources_path: str | Path,
    processed_entries: Generator[DrawingSource, None, None],
    project_id: int,
    detail_level: str = DEFAULT_DETAIL_LEVEL,
) -> int:
    """Save an entity tree to the database from processed entries.

    Args:
        sources_path: Root scan path.
        processed_entries: Processed entries with ready-to-store summaries.
        project_id: Project identifier in the database.

    Returns:
        Number of created entities.

    Raises:
        errors.FolderNotFound: If the parent directory is missing for a file or ZIP.
    """

    logger.info("Saving results to the database")
    with session_factory() as session:

        root = Path(sources_path)
        folders, created_entities = create_folders_tree(session, root, project_id)

        zip_entities: dict[str, Entity] = {}

        for entry in processed_entries:
            source_ref = str(entry.source)
            logger.info("Saving entities for file: %s", source_ref)
            file_type = EntityType.FILE if entry.kind == "file" else EntityType.ZIPPED_FILE

            if entry.kind == "zipped_file":
                zip_source = str(entry.source)
                zip_parent_rel = str(getattr(entry, "zip_parent_rel", ""))
                zip_parent_entity = folders.get(zip_parent_rel)
                if zip_parent_entity is None:
                    raise errors.FolderNotFound(f"Parent directory for ZIP not found: {zip_parent_rel}")

                zip_entity = zip_entities.get(zip_source)
                if zip_entity is None:
                    zip_entity = Entity(
                        parent_id=zip_parent_entity.id,
                        project_id=project_id,
                        name=Path(zip_source).name,
                        description=f"ZIP archive: {zip_source}",
                        entity_type=EntityType.ZIPFILE,
                        data={"path": zip_source},
                        embedding_data=build_entity_embedding(f"ZIP archive: {zip_source}"),
                    )
                    session.add(zip_entity)
                    session.flush()
                    zip_entities[zip_source] = zip_entity
                    created_entities += 1
                parent_entity = zip_entity
            else:
                parent_rel = str(getattr(entry, "parent_rel", ""))
                parent_entity = folders.get(parent_rel)
                if parent_entity is None:
                    raise errors.FolderNotFound(f"Parent directory for file not found: {parent_rel}")

            file_entity = Entity(
                parent_id=parent_entity.id,
                project_id=project_id,
                name=str(getattr(entry, "name", "")),
                description=f"Source file: {source_ref}",
                entity_type=file_type,
                data={"source_ref": source_ref},
                entity_md5=str(getattr(entry, "entity_md5", "")) or None,
                embedding_data=build_entity_embedding(f"Source file: {source_ref}"),
            )
            session.add(file_entity)
            session.flush()
            created_entities += 1

            summary = cast(dict[str, list[dict[str, object]]], getattr(entry, "summary", {}))
            layer_entities_by_key: dict[str, Entity] = {}
            layout_entities_by_name: dict[str, int] = {}
            logger.info("Layouts (%d)", len(summary.get("layouts", [])))
            for layout in summary["layouts"]:
                layout_name = str(layout["name"])
                layout_entity = Entity(
                    parent_id=file_entity.id,
                    file_id=file_entity.id,
                    project_id=project_id,
                    name=layout_name,
                    description="",
                    entity_type=EntityType.LAYOUT,
                    data={},
                    embedding_data=build_entity_embedding(f"Layout {layout_name}"),
                )
                session.add(layout_entity)
                session.flush()
                layout_entities_by_name[layout_name] = layout_entity.id
                created_entities += 1

            logger.info("Layers (%d)", len(summary.get("layers", [])))
            for layer in summary["layers"]:
                layer_name = str(layer["name"])
                layer_entity = Entity(
                    parent_id=file_entity.id,
                    file_id=file_entity.id,
                    project_id=project_id,
                    name=layer_name,
                    description="",
                    entity_type=EntityType.LAYER,
                    data=layer.get("data", {}),
                    embedding_data=build_entity_embedding(f"Layer {layer_name}"),
                )
                session.add(layer_entity)
                session.flush()
                layer_entities_by_key[layer_name] = layer_entity
                created_entities += 1

            block_entities_by_name: dict[str, int] = {}
            logger.info("Blocks (%d)", len(summary.get("blocks", [])))
            for block in summary["blocks"]:
                block_name = str(block["name"])

                block_description, block_data = get_block_payload(block)

                block_entity = Entity(
                    parent_id=file_entity.id,
                    file_id=file_entity.id,
                    project_id=project_id,
                    name=block_name,
                    description=block_description,
                    entity_type=EntityType.BLOCK,
                    data=block_data,
                    is_table=bool(block.get("is_table")),
                    embedding_data=build_entity_embedding(f"Block {block_name}"),
                )
                session.add(block_entity)
                session.flush()
                block_entities_by_name[block_name] = block_entity.id
                created_entities += 1

            block_links = summary.get("block_links", {})
            if not isinstance(block_links, dict):
                block_links = {}
                
            for block_name, linked_blocks in block_links.items():
                block_entity_id = block_entities_by_name.get(block_name)
                if block_entity_id:
                    for linked_block in linked_blocks:
                        linked_block_entity_id = block_entities_by_name.get(linked_block) or layout_entities_by_name.get(linked_block)
                        if linked_block_entity_id:
                            session.add(
                                EntityToEntity(
                                    dst_id=linked_block_entity_id,
                                    src_id=block_entity_id,
                                    link="contains",
                                )
                            )

            block_layers = summary.get("block_layers", {})
            if not isinstance(block_layers, dict):
                block_layers = {}
            for block_name, layers in block_layers.items():
                block_entity_id = block_entities_by_name.get(block_name)
                if block_entity_id:
                    for layer_name in layers:
                        layer_entity = layer_entities_by_key.get(layer_name)
                        if layer_entity:
                            session.add(
                                EntityToEntity(
                                    dst_id=layer_entity.id,
                                    src_id=block_entity_id,
                                    link="has_layer",
                                )
                            )

            primitives = summary.get("primitives", [])
            for item in primitives:
                if not isinstance(item, dict):
                    continue
                e_children = item.pop("children", [])
                if e_children:
                    for x in e_children:
                        x["is_virtual"] = True
                        primitives.append(x)

            primitive_batch: list[Entity] = []
            primitive_layer_links: list[tuple[Entity, Entity]] = []

            logger.info("Primitives (%d)", len(primitives))

            for idx, primitive in enumerate(primitives, start=1):
                primitive_payload = dict(primitive)
                name = None
                if "name" in primitive_payload:
                    name = str(primitive_payload.pop("name")).strip()

                layer_name = primitive_payload.get("layer")
                layer_entity = (
                    layer_entities_by_key.get(layer_name)
                    if isinstance(layer_name, str)
                    else None
                )
                parent = primitive_payload.pop("parent", None)
                layout_entity = primitive_payload.pop("layout", None)
                layout_name = None
                if isinstance(layout_entity, str):
                    layout_name = layout_entity
                elif hasattr(layout_entity, "name") and isinstance(layout_entity.name, str):
                    layout_name = layout_entity.name

                parent_entity_id = None
                _block_name = None
                if hasattr(parent, "name") and isinstance(parent.name, str):
                    _block_name = parent.name
                elif hasattr(parent, "dxf") and parent.dxf.hasattr("name") and isinstance(parent.dxf.name, str):
                    _block_name = parent.dxf.name
                    
                if _block_name:
                    parent_entity_id = (
                        block_entities_by_name.get(_block_name)
                        if isinstance(_block_name, str)
                        else None
                    )
 
                if parent_entity_id is None:
                    parent_entity_id = file_entity.id

                description = primitive_payload.pop("description", None)
                geometry = primitive_payload.pop("geom", None)
                primitive_data = get_primitive_payload(
                    primitive_payload,
                    detail_level=detail_level,
                    block_name=_block_name,
                    layout_name=layout_name,
                    description=description,
                    geometry=geometry,
                )

                primitive_entity = Entity(
                    parent_id=parent_entity_id,
                    file_id=file_entity.id,
                    project_id=project_id,
                    name=name,
                    description=description,
                    entity_type=coerce_entity_type(primitive_payload.get("type")),
                    geom=geometry,
                    is_virtual=primitive_payload.get("is_virtual", False)
                )

                if primitive_data:
                    # FIXME: required to solve it
                    # primitive_entity.data = primitive_data
                    pass

                primitive_batch.append(primitive_entity)

                if layer_entity is not None:
                    primitive_layer_links.append((primitive_entity, layer_entity))

                if idx % PRIMITIVE_BATCH_SIZE == 0:
                    created_entities += flush_primitives_batch(
                        session,
                        primitive_batch,
                        primitive_layer_links,
                        processed_count=idx,
                        primitives_total=len(primitives),
                    )

            if primitive_batch:
                created_entities += flush_primitives_batch(
                    session,
                    primitive_batch,
                    primitive_layer_links,
                    processed_count=len(primitives),
                    primitives_total=len(primitives),
                    final=True,
                )
            else:
                session.commit()

    return created_entities


def parse_drawing(
    sources_path: Path,
    project_name: str | None = None,
    dry: bool = False,
    detail_level: str = DEFAULT_DETAIL_LEVEL,
) -> dict[str, object]:
    """Walk a directory or file, parse DWG/DXF, and save the entity tree.

    Args:
        sources_path: Path to a drawing file or directory.
        project_name: Name of an existing database project.
        dry: Parse without saving results to the database.

    Returns:
        Summary with created entity count and discovered file count.

    Raises:
        errors.ObjectNotFound: If project_name is missing when dry=False.
        errors.UnsupportedFileType: If an unsupported file format is provided.
        errors.FileNotFound: If the path does not exist or contains no DWG/DXF/DXB files.
    """

    logger.info("Starting processing")

    project_id = None
    if not dry:
        with session_factory() as session:
            result = session.execute(
                select(Project.id).where(Project.name == project_name)
            )
            project_id = result.scalar_one_or_none()

        if project_id is None:
            raise errors.ObjectNotFound(f"Project named '{project_name}' was not found.")

    if sources_path.is_file():
        logger.info("Processing file: %s", sources_path)
        suffix = sources_path.suffix.lower()
        if suffix not in {".dwg", ".dxf", ".dxb"}:
            raise errors.UnsupportedFileType("Only DWG, DXF, and DXB files are supported.")

        drawing_sources = [
            DrawingSource(
                kind="file",
                root=str(sources_path),
                source=str(sources_path),
                name=sources_path.name,
                file_type=suffix,
                parent_rel="",
            ),
        ]
    elif sources_path.is_dir():
        logger.info("Processing directory: %s", sources_path)
        drawing_sources = list(DrawingProcessor(sources_path).walk(sources_path))
        if not drawing_sources:
            raise errors.FileNotFound(
                f"No DWG / DXF / DXB files were found in {sources_path} (including ZIP archives)."
            )
    else:
        raise errors.FileNotFound(f"Path {sources_path} was not found.")

    processed_entries = (process_entry(entry) for entry in drawing_sources)

    created_entities = 0
    if not dry:
        created_entities = save_to_db(
            sources_path,
            processed_entries,
            project_id=project_id,
            detail_level=detail_level,
        )

    return {
        "job_id": None,
        "project_id": project_id,
        "file_count": len(drawing_sources),
        "workers": 1,
        "mode": "dry" if dry else "direct",
        "detail_level": detail_level,
        "created_entities": created_entities,
    }


__all__ = ["DrawingProcessor", "parse_drawing"]
