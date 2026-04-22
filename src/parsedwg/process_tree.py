"""Обход каталога DWG/DXF и сохранение дерева сущностей в БД."""

from __future__ import annotations

from typing import Any, Generator, Protocol, cast

import asyncio
import hashlib
import logging
import multiprocessing as mp
import queue
import re
import tempfile
import zipfile

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ezdxf.document import Drawing
from ezdxf.addons.odafc import readfile as read_odafc
from ezdxf.filemanagement import readfile
from sqlalchemy import func, select

from .db import async_session_factory
from .orm import Entity, EntityToEntity, EntityType, Project
from .redis_queue import load_converted, new_job_id, push_converted, push_sources
from .table_analysis import TextClusterAnalyzer
from .utils import get_workers_number

logger = logging.getLogger(__name__)

type JobEntry = dict[str, str]
type ProcessedEntry = dict[str, object]
type NameTagsAIConfig = dict[str, str]


class NameTagsExtractor(Protocol):
    def extract(self, text: str) -> list[str]: ...


class _QueueLike(Protocol):
    def put(self, item: object) -> None: ...

    def get(self) -> object: ...


_QUEUE_EVENT_KEY = "__queue_event__"
_QUEUE_EVENT_DONE = "worker_done"
_QUEUE_EVENT_ERROR = "worker_error"


def _should_skip_block(block_name: str) -> bool:
    return (
        block_name.startswith("*D")
        or block_name.startswith("*U")
        or block_name.startswith("A$")
    )


class DWGTreeProcessor:
    """Обходит каталог и собирает задания на разбор DWG/DXF."""

    def __init__(self, source_path: Path, root_path: Path | None = None):
        self.source_path = source_path
        self.root_path = root_path or source_path
        if not self.root_path.exists():
            raise FileNotFoundError(f"Путь {self.root_path} не найден.")

    @staticmethod
    def file_md5(path: Path) -> str:
        digest = hashlib.md5(usedforsecurity=False)
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def walk(self, root_path: Path) -> Generator[JobEntry, None, None]:
        for file_path in sorted(path for path in root_path.rglob("*") if path.is_file()):
            suffix = file_path.suffix.lower()
            if suffix in {".dwg", ".dxf", ".dxb"}:
                parent_rel = file_path.parent.relative_to(root_path)
                parent_rel_str = "" if str(parent_rel) == "." else parent_rel.as_posix()
                yield {
                    "kind": "file",
                    "root": str(root_path),
                    "source": str(file_path),
                    "name": file_path.name,
                    "file_type": suffix,
                    "parent_rel": parent_rel_str,
                }
                continue

            if suffix != ".zip":
                continue

            zip_parent_rel = file_path.parent.relative_to(root_path)
            zip_parent_rel_str = "" if str(zip_parent_rel) == "." else zip_parent_rel.as_posix()
            try:
                with zipfile.ZipFile(file_path) as archive:
                    for member_name in sorted(info.filename for info in archive.infolist()):
                        if member_name.endswith("/"):
                            continue
                        member_suffix = Path(member_name).suffix.lower()
                        if member_suffix not in {".dwg", ".dxf", ".dxb"}:
                            continue
                        yield {
                            "kind": "zipped_file",
                            "root": str(root_path),
                            "source": str(file_path),
                            "member": member_name,
                            "name": Path(member_name).name,
                            "file_type": member_suffix,
                            "zip_parent_rel": zip_parent_rel_str,
                            "parent_rel": zip_parent_rel_str,
                        }
            except zipfile.BadZipFile:
                logger.warning("Пропускаем поврежденный ZIP: %s", file_path)


def _split_to_batches(entries: list[JobEntry], workers: int) -> list[list[JobEntry]]:
    normalized_workers = max(1, workers)
    batches: list[list[JobEntry]] = [[] for _ in range(normalized_workers)]
    for index, entry in enumerate(entries):
        batches[index % normalized_workers].append(entry)
    return [batch for batch in batches if batch]


def _extract_member_from_zip(zip_path: Path, member: str, temp_dir: Path) -> Path:
    target_path = temp_dir / Path(member).name
    with zipfile.ZipFile(zip_path) as archive:
        data = archive.read(member)
    target_path.write_bytes(data)
    return target_path


def read_drawing(path: Path):
    suffix = path.suffix.lower()
    if suffix == ".dwg":
        return read_odafc(path, "ACAD2018")
    return readfile(path)


def _queue_done_event() -> dict[str, str]:
    return {_QUEUE_EVENT_KEY: _QUEUE_EVENT_DONE}


def _queue_error_event(message: str) -> dict[str, str]:
    return {_QUEUE_EVENT_KEY: _QUEUE_EVENT_ERROR, "message": message}


def _queue_event_type(item: object) -> str | None:
    if not isinstance(item, dict):
        return None
    value = item.get(_QUEUE_EVENT_KEY)
    return str(value) if value is not None else None


def _build_name_tags_extractor_from_config(
    name_tags_config: NameTagsAIConfig | None,
) -> NameTagsExtractor | None:
    if name_tags_config is None:
        return None

    from .langchain_name_tags import LangChainAgentConfig, LangChainNameTagsExtractor

    config = LangChainAgentConfig(
        model=name_tags_config["model"],
        base_url=name_tags_config["base_url"],
        api_key=name_tags_config["api_key"],
    )
    return LangChainNameTagsExtractor.from_config(config)


def _build_entity_text(text_value: str | None):
    if text_value is None or not text_value.strip():
        return None
    return func.to_tsvector("russian", text_value)


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


def collect_layout_layers(doc, layout) -> list[str]:
    layers: set[str] = set()
    for entity in layout:
        layers.update(collect_entity_layers(doc, entity))
    return sorted(layers)


def _format_point(point: object | None) -> str:
    if point is None:
        return "n/a"

    x = getattr(point, "x", None)
    y = getattr(point, "y", None)
    z = getattr(point, "z", 0.0)
    if x is not None and y is not None:
        return f"({x:.2f}, {y:.2f}, {z:.2f})"

    if isinstance(point, (tuple, list)) and len(point) >= 2:
        try:
            px = float(point[0])
            py = float(point[1])
            pz = float(point[2]) if len(point) >= 3 else 0.0
        except (TypeError, ValueError):
            return str(point)
        return f"({px:.2f}, {py:.2f}, {pz:.2f})"

    return str(point)


def _is_point_like(value: object) -> bool:
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


def _get_text_content(entity) -> str:
    entity_type = entity.dxftype()
    if entity_type == "TEXT" and entity.dxf.hasattr("text"):
        return str(entity.dxf.text).strip()

    if entity_type == "MTEXT":
        plain_text = getattr(entity, "plain_text", None)
        if callable(plain_text):
            return str(plain_text()).strip()

    return ""


def _describe_entity(entity) -> str:
    params: dict[str, str] = {"type": entity.dxftype()}

    if entity.dxftype() == "INSERT" and entity.dxf.hasattr("name"):
        params["block"] = str(entity.dxf.name)

    for attr_name, value in entity.dxf.all_existing_dxf_attribs().items():
        if _is_point_like(value):
            params[attr_name] = _format_point(value)

    if entity.dxftype() == "LWPOLYLINE":
        get_points = getattr(entity, "get_points", None)
        if callable(get_points):
            raw_points = get_points("xy")
            if isinstance(raw_points, (list, tuple)):
                points = [
                    f"({float(point[0]):.2f}, {float(point[1]):.2f}, 0.00)"
                    for point in raw_points
                ]
                if points:
                    params["points"] = f"[{', '.join(points)}]"

    text_value = _get_text_content(entity)
    if text_value:
        params["text"] = re.sub(r"\s+", " ", text_value).strip()[:200]

    rendered: list[str] = []
    for key, value in params.items():
        if key in {"block", "text"}:
            rendered.append(f"{key}={value!r}")
        else:
            rendered.append(f"{key}={value}")
    return ", ".join(rendered)


def _collect_text_primitives(doc) -> list[dict[str, str]]:
    primitives: list[dict[str, str]] = []

    for block in doc.blocks:
        block_name = str(block.name)
        if block_name.startswith("*"):
            continue
        if _should_skip_block(block_name):
            continue

        for entity in block:
            entity_type = entity.dxftype()
            if entity_type not in {"TEXT", "MTEXT", "INSERT"}:
                continue

            location = "n/a"
            if entity.dxf.hasattr("insert"):
                location = _format_point(getattr(entity.dxf, "insert"))

            if entity_type == "INSERT":
                target_block = ""
                if entity.dxf.hasattr("name"):
                    target_block = str(entity.dxf.name)

                primitives.append(
                    {
                        "block": block_name,
                        "type": entity_type,
                        "text": target_block,
                        "location": location,
                        "layer": str(getattr(entity.dxf, "layer", "")),
                        "target_block": target_block,
                    }
                )
                continue

            text_value = _get_text_content(entity)
            if not text_value:
                continue

            primitives.append(
                {
                    "block": block_name,
                    "type": entity_type,
                    "text": re.sub(r"\s+", " ", text_value).strip(),
                    "location": location,
                    "layer": str(getattr(entity.dxf, "layer", "")),
                }
            )

    return primitives


def _collect_layout_insert_primitives(doc) -> list[dict[str, str]]:
    primitives: list[dict[str, str]] = []

    for layout in doc.layouts:
        layout_name = str(layout.name)
        for entity in layout:
            if entity.dxftype() != "INSERT" or not entity.dxf.hasattr("name"):
                continue

            target_block = str(entity.dxf.name)
            if _should_skip_block(target_block):
                continue

            location = "n/a"
            if entity.dxf.hasattr("insert"):
                location = _format_point(getattr(entity.dxf, "insert"))

            primitives.append(
                {
                    "block": target_block,
                    "type": "INSERT",
                    "text": target_block,
                    "location": location,
                    "layer": str(getattr(entity.dxf, "layer", "")),
                    "target_block": target_block,
                    "layout": layout_name,
                }
            )

    return primitives


def _enrich_primitives_with_name_tags(
    primitives: list[dict[str, str]],
    name_tags_extractor: NameTagsExtractor,
) -> list[dict[str, object]]:
    enriched: list[dict[str, object]] = []
    for primitive in primitives:
        payload: dict[str, object] = dict(primitive)
        if primitive.get("type") not in {"TEXT", "MTEXT"}:
            enriched.append(payload)
            continue

        text = primitive.get("text", "").strip()
        if text:
            tags = [tag.strip() for tag in name_tags_extractor.extract(text) if tag.strip()]
            if tags:
                payload["ai_name_tags"] = sorted(set(tags))
        enriched.append(payload)
    return enriched


def collect_drawing_summary(
    drawing: Drawing,
    name_tags_extractor: NameTagsExtractor | None = None,
) -> dict[str, Any]:
    """Собирает информацию о Layouts, Blocks и примитивах из документа."""
    
    layouts: list[dict[str, object]] = []
    for layout in drawing.layouts:
        layers = collect_layout_layers(drawing, layout)
        layouts.append({"name": layout.name, "layers": layers})

    blocks: list[dict[str, object]] = []
    for block in drawing.blocks:
        table_stats = TextClusterAnalyzer.analyze_table(block)
        blocks.append(
            {
                "name": block.name,
                "entity_count": sum(1 for _ in block),
                "is_table": table_stats.is_table,
                "table": {
                    "title": table_stats.title,
                    "rows": table_stats.rows,
                    "total_texts": table_stats.total_texts,
                    "table_like_texts": table_stats.table_like_texts,
                    "x_clusters": len(table_stats.x_clusters),
                    "y_clusters": len(table_stats.y_clusters),
                },
            }
        )

    primitives = _collect_text_primitives(drawing)
    primitives.extend(_collect_layout_insert_primitives(drawing))
    if name_tags_extractor is not None:
        primitives_payload = _enrich_primitives_with_name_tags(primitives, name_tags_extractor)
    else:
        primitives_payload = cast(list[dict[str, object]], primitives)

    return {
        "layouts": layouts,
        "blocks": blocks,
        "primitives": primitives_payload,
    }


def collect_dxf_summary(
    drawing_path: Path,
    name_tags_extractor: NameTagsExtractor | None = None,
) -> dict[str, Any]:
    """Собирает информацию о Layouts, Blocks и примитивах из DWG/DXF-файла."""

    # Чтение файла DWG / DXF
    doc = read_drawing(drawing_path)
    return collect_drawing_summary(doc, name_tags_extractor=name_tags_extractor)


def process_entry(
    entry: JobEntry,
    name_tags_extractor: NameTagsExtractor | None = None,
) -> ProcessedEntry:
    source = Path(entry["source"])

    with tempfile.TemporaryDirectory(prefix="parsedwg-process-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)

        if entry["kind"] == "file":
            source_ref = entry["source"]
            working_path = source
            file_md5 = DWGTreeProcessor.file_md5(working_path)
        else:
            member_name = entry.get("member")
            if member_name is None:
                raise ValueError("Для zipped_file не указан member.")
            working_path = _extract_member_from_zip(source, member_name, temp_dir)
            source_ref = f"{entry['source']}::{member_name}"
            file_md5 = DWGTreeProcessor.file_md5(working_path)

        summary = collect_dxf_summary(working_path, name_tags_extractor=name_tags_extractor)

    processed_entry: ProcessedEntry = {
        **entry,
        "source_ref": source_ref,
        "file_md5": file_md5,
        "summary": summary,
    }
    return processed_entry


def process_batch(
    batch: list[JobEntry],
    processed_queue: _QueueLike | None = None,
    job_id: str | None = None,
    name_tags_config: NameTagsAIConfig | None = None,
) -> list[ProcessedEntry]:
    processed: list[ProcessedEntry] = []
    try:
        name_tags_extractor = _build_name_tags_extractor_from_config(name_tags_config)
        for entry in batch:
            processed_entry = process_entry(entry, name_tags_extractor=name_tags_extractor)
            processed.append(processed_entry)
            if job_id is not None:
                push_converted(job_id, cast(dict[str, str], processed_entry))
            if processed_queue is not None:
                processed_queue.put(processed_entry)
    except Exception as error:
        if processed_queue is not None:
            processed_queue.put(_queue_error_event(str(error)))
        raise
    finally:
        if processed_queue is not None:
            processed_queue.put(_queue_done_event())

    return processed


async def _create_folders_tree(
    session,
    root_path: Path,
    project_id,
) -> tuple[dict[str, Entity], int]:
    root_entity = Entity(
        name=root_path.name or str(root_path),
        description=f"Источник сканирования: {root_path}",
        entity_text=_build_entity_text(f"Источник сканирования: {root_path}"),
        entity_type=EntityType.folder,
        data={"path": str(root_path)},
        start_from=str(root_path),
        project_id=project_id,
        created_at=func.now(),

    )
    session.add(root_entity)
    await session.flush()

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
            description=f"Каталог: {dir_path}",
            entity_text=_build_entity_text(f"Каталог: {dir_path}"),
            entity_type=EntityType.folder,
            data={"path": str(dir_path)},
            start_from=str(dir_path),
        )
        session.add(folder_entity)
        await session.flush()
        session.add(
            EntityToEntity(
                src_id=parent_entity.id,
                dst_id=folder_entity.id,
                link="contains_folder",
            )
        )
        folders[rel] = folder_entity
        created += 1

    return folders, created


async def save_tree_to_db(
    root_path: str,
    processed_queue: _QueueLike,
    producer_count: int,
    project_name: str,
    project_description: str | None = None,
    created_by: str | None = None,
) -> tuple[str, int]:
    """Сохраняет дерево сущностей в БД, читая обработанные задания из очереди. 
    Возвращает ID проекта и количество созданных сущностей."""

    async with async_session_factory() as session:
        # Выбираем существующий проект или создаем новый
        result = await session.execute(
            select(Project.id).where(Project.name == project_name)
        )
        project_id = result.scalar_one_or_none()

        if project_id is None:
            project = Project(
                name=project_name,
                description=project_description,
                created_by=created_by,
            )
            session.add(project)
            await session.flush()
            project_id = project.id

        root = Path(root_path)
        folders, created_entities = await _create_folders_tree(session, root, project_id)

        zip_entities: dict[str, Entity] = {}
        completed_producers = 0

        while completed_producers < producer_count:
            queue_item = processed_queue.get()
            event_type = _queue_event_type(queue_item)
            if event_type == _QUEUE_EVENT_DONE:
                completed_producers += 1
                continue
            if event_type == _QUEUE_EVENT_ERROR:
                message = "Неизвестная ошибка обработки"
                if isinstance(queue_item, dict):
                    message = str(queue_item.get("message", message))
                raise RuntimeError(message)

            entry = cast(ProcessedEntry, queue_item)
            source_ref = str(entry["source_ref"])
            kind = str(entry["kind"])
            file_type = EntityType.file if kind == "file" else EntityType.zipped_file

            if kind == "zipped_file":
                zip_source = str(entry["source"])
                zip_parent_rel = str(entry.get("zip_parent_rel", ""))
                zip_parent_entity = folders.get(zip_parent_rel)
                if zip_parent_entity is None:
                    raise RuntimeError(f"Не найден родительский каталог для ZIP: {zip_parent_rel}")

                zip_entity = zip_entities.get(zip_source)
                if zip_entity is None:
                    zip_entity = Entity(
                        parent_id=zip_parent_entity.id,
                        project_id=project_id,
                        name=Path(zip_source).name,
                        description=f"ZIP-архив: {zip_source}",
                        entity_text=_build_entity_text(f"ZIP-архив: {zip_source}"),
                        entity_type=EntityType.zipfile,
                        data={"path": zip_source},
                        start_from=zip_source,
                    )
                    session.add(zip_entity)
                    await session.flush()
                    session.add(
                        EntityToEntity(
                            src_id=zip_parent_entity.id,
                            dst_id=zip_entity.id,
                            link="contains_zip",
                        )
                    )
                    zip_entities[zip_source] = zip_entity
                    created_entities += 1
                parent_entity = zip_entity
            else:
                parent_rel = str(entry.get("parent_rel", ""))
                parent_entity = folders.get(parent_rel)
                if parent_entity is None:
                    raise RuntimeError(f"Не найден родительский каталог для файла: {parent_rel}")

            file_entity = Entity(
                parent_id=parent_entity.id,
                project_id=project_id,
                name=str(entry["name"]),
                description=f"Исходный файл: {source_ref}",
                entity_text=_build_entity_text(f"Исходный файл: {source_ref}"),
                entity_type=file_type,
                data={"source_ref": source_ref},
                file_md5=str(entry.get("file_md5", "")) or None,
                start_from=source_ref,
            )
            session.add(file_entity)
            await session.flush()
            session.add(
                EntityToEntity(
                    src_id=parent_entity.id,
                    dst_id=file_entity.id,
                    link="contains_file",
                )
            )
            created_entities += 1

            summary = cast(dict[str, list[dict[str, object]]], entry["summary"])
            layer_entities_by_key: dict[tuple[str, str], Entity] = {}
            for layout in summary["layouts"]:
                layout_name = str(layout["name"])
                layout_entity = Entity(
                    parent_id=file_entity.id,
                    project_id=project_id,
                    name=layout_name,
                    description=f"Layout файла {entry['name']}",
                    entity_text=_build_entity_text(f"Layout файла {entry['name']}"),
                    entity_type=EntityType.layout,
                    data={},
                    start_from=source_ref,
                )
                session.add(layout_entity)
                await session.flush()
                session.add(
                    EntityToEntity(
                        src_id=file_entity.id,
                        dst_id=layout_entity.id,
                        link="contains_layout",
                    )
                )
                created_entities += 1

                for layer_name in cast(list[str], layout["layers"]):
                    layer_name_str = str(layer_name)
                    layer_entity = Entity(
                        parent_id=layout_entity.id,
                        project_id=project_id,
                        name=layer_name_str,
                        description=f"Layer layout {layout_name}",
                        entity_text=_build_entity_text(f"Layer layout {layout_name}"),
                        entity_type=EntityType.layer,
                        data={"layout": layout_name},
                        start_from=source_ref,
                    )
                    session.add(layer_entity)
                    await session.flush()
                    session.add(
                        EntityToEntity(
                            src_id=layout_entity.id,
                            dst_id=layer_entity.id,
                            link="contains_layer",
                        )
                    )
                    layer_entities_by_key[(layout_name, layer_name_str)] = layer_entity
                    created_entities += 1

            block_entities_by_name: dict[str, Entity] = {}
            layer_block_links: set[tuple[object, object]] = set()
            for block in summary["blocks"]:
                block_name = str(block["name"])
                if _should_skip_block(block_name):
                    continue

                block_data: dict[str, object] = {
                    "entity_count": block["entity_count"],
                }
                if block.get("is_table"):
                    block_data["table"] = block["table"]

                block_entity = Entity(
                    parent_id=file_entity.id,
                    project_id=project_id,
                    name=block_name,
                    description=f"Block файла {entry['name']}",
                    entity_text=_build_entity_text(f"Block файла {entry['name']}"),
                    entity_type=EntityType.block,
                    data=block_data,
                    is_table=cast(bool, block["is_table"]),
                    start_from=source_ref,
                )
                session.add(block_entity)
                await session.flush()
                session.add(
                    EntityToEntity(
                        src_id=file_entity.id,
                        dst_id=block_entity.id,
                        link="contains_block",
                    )
                )
                block_entities_by_name[block_name] = block_entity
                created_entities += 1

            for primitive in summary["primitives"]:
                block_name = str(primitive["block"])
                parent_block_entity = block_entities_by_name.get(block_name)
                if parent_block_entity is None:
                    logger.warning(
                        "Пропускаем примитив %s: не найден block entity %s",
                        primitive.get("text", ""),
                        block_name,
                    )
                    continue

                primitive_data = {
                    "block": block_name,
                    "layer": primitive["layer"],
                    "location": primitive["location"],
                }
                layout_name = primitive.get("layout")
                if isinstance(layout_name, str) and layout_name:
                    primitive_data["layout"] = layout_name

                target_block = primitive.get("target_block")
                if isinstance(target_block, str) and target_block:
                    primitive_data["target_block"] = target_block

                ai_name_tags = primitive.get("ai_name_tags")
                if isinstance(ai_name_tags, list) and ai_name_tags:
                    primitive_data["ai_name_tags"] = ai_name_tags

                primitive_entity = Entity(
                    parent_id=parent_block_entity.id,
                    project_id=project_id,
                    name=str(primitive["type"]),
                    description=str(primitive["text"]),
                    entity_text=_build_entity_text(str(primitive["text"])),
                    entity_type=EntityType.primitive,
                    data=primitive_data,
                    start_from=source_ref,
                )
                session.add(primitive_entity)
                await session.flush()
                session.add(
                    EntityToEntity(
                        src_id=parent_block_entity.id,
                        dst_id=primitive_entity.id,
                        link="contains_primitive",
                    )
                )

                layer_name = primitive.get("layer")
                if isinstance(layout_name, str) and isinstance(layer_name, str):
                    layer_entity = layer_entities_by_key.get((layout_name, layer_name))
                    if layer_entity is not None:
                        relation_key = (layer_entity.id, parent_block_entity.id)
                        if relation_key not in layer_block_links:
                            session.add(
                                EntityToEntity(
                                    src_id=layer_entity.id,
                                    dst_id=parent_block_entity.id,
                                    link="contains_block",
                                )
                            )
                            layer_block_links.add(relation_key)

                created_entities += 1

            await session.commit()

    return str(project_id), created_entities


def process_queue(
    processed_queue: _QueueLike,
    root_path: str,
    producer_count: int,
    project_name: str,
    project_description: str | None,
    created_by: str | None,
) -> tuple[str, int]:
    """Проходит по очереди обработанных заданий, сохраняет дерево в БД и возвращает 
    ID проекта и количество созданных сущностей."""

    return asyncio.run(
        save_tree_to_db(
            root_path=root_path,
            processed_queue=processed_queue,
            producer_count=producer_count,
            project_name=project_name,
            project_description=project_description,
            created_by=created_by,
        )
    )


def run_process_tree(
    source_path: Path,
    conversion_workers: int = 2,
    project_name: str | None = None,
    project_description: str | None = None,
    created_by: str | None = None,
    name_tags_config: NameTagsAIConfig | None = None,
    use_process_pool: bool = True,
) -> dict[str, object]:
    """Обходит каталог/файл, разбирает DWG/DXF в пуле процессов и сохраняет дерево в БД."""

    root_path = source_path if source_path.is_dir() else source_path.parent
    if source_path.is_file():
        suffix = source_path.suffix.lower()
        if suffix not in {".dwg", ".dxf", ".dxb"}:
            raise ValueError("Поддерживаются только файлы DWG, DXF, DXB.")
        entries = [
            {
                "kind": "file",
                "root": str(root_path),
                "source": str(source_path),
                "name": source_path.name,
                "file_type": suffix,
                "parent_rel": "",
            }
        ]
    elif source_path.is_dir():
        entries = list(DWGTreeProcessor(source_path).walk(source_path))
        if not entries:
            raise ValueError(
                f"В каталоге {source_path} не найдено DWG / DXF / DXB-файлов (включая ZIP)."
            )
    else:
        raise ValueError(f"Путь {source_path} не найден.")

    job_id = new_job_id()
    push_sources(job_id, entries)
    logger.info("Список файлов сохранён в Redis, job_id=%s, count=%d", job_id, len(entries))

    effective_workers = get_workers_number(conversion_workers)
    batches = _split_to_batches(entries, workers=effective_workers)

    processed_entries: list[ProcessedEntry] = []
    if use_process_pool:
        with mp.Manager() as manager:
            processed_queue = manager.Queue()

            with ProcessPoolExecutor(max_workers=max(2, effective_workers + 1)) as executor:
                ingest_future = executor.submit(
                    process_queue,
                    processed_queue,
                    str(root_path),
                    len(batches),
                    project_name or root_path.name or str(root_path),
                    project_description,
                    created_by,
                )
                futures = [
                    executor.submit(
                        process_batch,
                        batch,
                        processed_queue,
                        job_id,
                        name_tags_config,
                    )
                    for batch in batches
                ]
                for future in futures:
                    processed_entries.extend(future.result())

                project_id, created_entities = ingest_future.result()
    else:
        logger.info("Запущен последовательный режим обработки без ProcessPoolExecutor.")
        processed_queue: _QueueLike = queue.Queue()
        for batch in batches:
            processed_entries.extend(
                process_batch(
                    batch,
                    processed_queue,
                    job_id,
                    name_tags_config,
                )
            )
        project_id, created_entities = process_queue(
            processed_queue,
            str(root_path),
            len(batches),
            project_name or root_path.name or str(root_path),
            project_description,
            created_by,
        )

    processed_entries.sort(key=lambda item: str(item.get("source_ref", "")))
    redis_processed_count = len(load_converted(job_id))
    logger.info(
        "Обработка завершена: job_id=%s, files=%d (redis=%d)",
        job_id,
        len(processed_entries),
        redis_processed_count,
    )

    mode = "process_pool" if use_process_pool else "sequential"

    return {
        "job_id": job_id,
        "project_id": project_id,
        "file_count": len(entries),
        "processed_count": len(processed_entries),
        "workers": effective_workers,
        "mode": mode,
        "created_entities": created_entities,
    }


__all__ = ["DWGTreeProcessor", "collect_dxf_summary", "run_process_tree", "_describe_entity"]
