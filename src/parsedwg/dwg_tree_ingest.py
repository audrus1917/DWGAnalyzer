from __future__ import annotations

from typing import Any, Generator

import asyncio
import hashlib
import json
import logging
import multiprocessing as mp
import re
import tempfile
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Protocol, cast

from ezdxf.filemanagement import readfile

from .db import async_session_factory
from .orm import Entity, EntityToEntity, EntityType
from .parsers import _convert_dwg_to_dxf
from .table_analysis import TextClusterAnalyzer

logger = logging.getLogger(__name__)

type ManifestEntry = dict[str, str]


class _QueueLike(Protocol):
    def put(self, item: object) -> None: ...

    def get(self) -> object: ...


_QUEUE_EVENT_KEY = "__queue_event__"
_QUEUE_EVENT_DONE = "converter_done"
_QUEUE_EVENT_ERROR = "converter_error"


def _compute_md5_hex(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_dwg_sources(root_path: Path) -> list[ManifestEntry]:
    if not root_path.exists():
        raise FileNotFoundError(f"Путь {root_path} не найден.")

    entries: list[ManifestEntry] = []
    for file_path in sorted(path for path in root_path.rglob("*") if path.is_file()):
        suffix = file_path.suffix.lower()
        if suffix == ".dwg":
            entries.append(
                {
                    "kind": "file",
                    "root": str(root_path),
                    "source": str(file_path),
                    "name": file_path.name,
                }
            )
            continue

        if suffix != ".zip":
            continue

        try:
            with zipfile.ZipFile(file_path) as archive:
                for member_name in sorted(info.filename for info in archive.infolist()):
                    if member_name.endswith("/"):
                        continue
                    if Path(member_name).suffix.lower() != ".dwg":
                        continue
                    entries.append(
                        {
                            "kind": "zipped_file",
                            "root": str(root_path),
                            "source": str(file_path),
                            "member": member_name,
                            "name": Path(member_name).name,
                        }
                    )
        except zipfile.BadZipFile:
            logger.warning("Пропускаем поврежденный ZIP: %s", file_path)

    return entries


def _write_temp_json_file(entries: list[ManifestEntry], prefix: str) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=prefix,
        suffix=".json",
        delete=False,
    ) as temp_file:
        json.dump(entries, temp_file, ensure_ascii=False, indent=2)
        return Path(temp_file.name)


def _load_manifest(manifest_path: str) -> list[ManifestEntry]:
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))


def _split_to_batches(entries: list[ManifestEntry], workers: int) -> list[list[ManifestEntry]]:
    normalized_workers = max(1, workers)
    batches: list[list[ManifestEntry]] = [[] for _ in range(normalized_workers)]
    for index, entry in enumerate(entries):
        batches[index % normalized_workers].append(entry)
    return [batch for batch in batches if batch]


def _resolve_conversion_workers(requested_workers: int) -> int:
    logical_cpus = max(1, mp.cpu_count())
    max_workers = max(1, logical_cpus - 1)
    auto_workers = max(1, min(max_workers, int(logical_cpus * 0.7)))

    if requested_workers <= 0:
        logger.info(
            "Автовыбор workers: logical_cpus=%s, conversion_workers=%s",
            logical_cpus,
            auto_workers,
        )
        return auto_workers

    if requested_workers > max_workers:
        logger.warning(
            "Запрошено workers=%s, ограничено до %s (logical_cpus=%s).",
            requested_workers,
            max_workers,
            logical_cpus,
        )
        return max_workers

    return requested_workers


def _extract_dwg_from_zip(zip_path: Path, member: str, temp_dir: Path) -> Path:
    target_path = temp_dir / Path(member).name
    with zipfile.ZipFile(zip_path) as archive:
        data = archive.read(member)
    target_path.write_bytes(data)
    return target_path


def _convert_entry(entry: ManifestEntry, converted_dir: str) -> ManifestEntry:
    source = Path(entry["source"])
    converted_root = Path(converted_dir)
    converted_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="parsedwg-convert-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        if entry["kind"] == "file":
            working_dwg = temp_dir / Path(entry["name"]).name
            working_dwg.write_bytes(source.read_bytes())
            source_ref = entry["source"]
        else:
            member_name = entry.get("member")
            if member_name is None:
                raise ValueError("Для zipped_file не указан member.")
            working_dwg = _extract_dwg_from_zip(source, member_name, temp_dir)
            source_ref = f"{entry['source']}::{member_name}"

        file_md5 = _compute_md5_hex(working_dwg)

        converted_temp_path = _convert_dwg_to_dxf(working_dwg)
        target_name = hashlib.sha1(source_ref.encode("utf-8")).hexdigest() + ".dxf"
        target_path = converted_root / target_name
        target_path.write_bytes(converted_temp_path.read_bytes())

    converted_entry: ManifestEntry = {
        **entry,
        "source_ref": source_ref,
        "dxf": str(target_path),
        "file_md5": file_md5,
    }
    return converted_entry


def _queue_done_event() -> ManifestEntry:
    return {_QUEUE_EVENT_KEY: _QUEUE_EVENT_DONE}


def _queue_error_event(message: str) -> ManifestEntry:
    return {_QUEUE_EVENT_KEY: _QUEUE_EVENT_ERROR, "message": message}


def _queue_event_type(item: object) -> str | None:
    if not isinstance(item, dict):
        return None
    value = item.get(_QUEUE_EVENT_KEY)
    return str(value) if value is not None else None


def _convert_batch(
    batch: list[ManifestEntry],
    converted_dir: str,
    converted_queue: _QueueLike | None = None,
) -> list[ManifestEntry]:
    converted: list[ManifestEntry] = []
    try:
        for entry in batch:
            converted_entry = _convert_entry(entry, converted_dir)
            converted.append(converted_entry)
            if converted_queue is not None:
                converted_queue.put(converted_entry)
    except Exception as error:
        if converted_queue is not None:
            converted_queue.put(_queue_error_event(str(error)))
        raise
    finally:
        if converted_queue is not None:
            converted_queue.put(_queue_done_event())

    return converted


def _collect_entity_layers(doc, entity, seen_blocks: set[str] | None = None) -> set[str]:
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
        layers.update(_collect_entity_layers(doc, nested_entity, nested_seen))
    return layers


def _collect_layout_layers(doc, layout) -> list[str]:
    layers: set[str] = set()
    for entity in layout:
        # logger.debug("  Entity: %s", _describe_entity(entity))
        layers.update(_collect_entity_layers(doc, entity))
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
        # Сохраняем в логе только первую строку текста, чтобы не раздувать debug-вывод.
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

    for layout in doc.layouts:
        for entity in layout:
            if entity.dxftype() not in {"TEXT", "MTEXT"}:
                continue

            text_value = _get_text_content(entity)
            if not text_value:
                continue

            location = "n/a"
            if entity.dxf.hasattr("insert"):
                location = _format_point(getattr(entity.dxf, "insert"))

            primitives.append(
                {
                    "type": entity.dxftype(),
                    "text": re.sub(r"\s+", " ", text_value).strip(),
                    "location": location,
                    "layout": str(layout.name),
                    "layer": str(getattr(entity.dxf, "layer", "")),
                }
            )

    return primitives


def collect_dxf_summary(dxf_path: Path) -> Generator[Any, None, None]:

    doc = readfile(dxf_path))
    layouts: list[dict[str, object]] = []
    for layout in doc.layouts:
        logger.debug("Layout: %s", layout.name)
        layers = _collect_layout_layers(doc, layout)
        layouts.append({"name": layout.name, "layers": layers})

    blocks: list[dict[str, object]] = []
    for block in doc.blocks:
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
        logger.debug("Block: %s", block.name)
        # for entity in block:
        #     logger.debug("  Entity: %s", _describe_entity(entity))

    primitives = _collect_text_primitives(doc)

    return {
        "layouts": layouts,
        "blocks": blocks,
        "primitives": cast(list[dict[str, object]], primitives),
    }


async def _save_tree_to_db(root_path: str, entries: list[ManifestEntry]) -> int:
    async with async_session_factory() as session:
        root_entity = Entity(
            name=Path(root_path).name or root_path,
            description=f"Источник сканирования: {root_path}",
            entity_type=EntityType.folder,
            data={"path": root_path},
            start_from=root_path,
        )
        session.add(root_entity)
        await session.flush()

        zip_entities: dict[str, Entity] = {}
        created_entities = 1

        for entry in entries:
            source_ref = entry["source_ref"]
            file_type = EntityType.file if entry["kind"] == "file" else EntityType.zipped_file

            parent_entity = root_entity
            if entry["kind"] == "zipped_file":
                zip_source = entry["source"]
                zip_entity = zip_entities.get(zip_source)
                if zip_entity is None:
                    zip_entity = Entity(
                        parent_id=root_entity.id,
                        name=Path(zip_source).name,
                        description=f"ZIP-архив: {zip_source}",
                        entity_type=EntityType.zipfile,
                        data={"path": zip_source},
                        start_from=zip_source,
                    )
                    session.add(zip_entity)
                    await session.flush()
                    session.add(
                        EntityToEntity(
                            src_id=root_entity.id,
                            dst_id=zip_entity.id,
                            link="contains_zip",
                        )
                    )
                    zip_entities[zip_source] = zip_entity
                    created_entities += 1
                parent_entity = zip_entity

            file_entity = Entity(
                parent_id=parent_entity.id,
                name=entry["name"],
                description=f"Исходный файл: {source_ref}",
                entity_type=file_type,
                data={"source_ref": source_ref, "dxf_path": entry["dxf"]},
                file_md5=entry.get("file_md5"),
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

            summary = collect_dxf_summary(Path(entry["dxf"]))
            for layout in summary["layouts"]:
                layout_entity = Entity(
                    parent_id=file_entity.id,
                    name=str(layout["name"]),
                    description=f"Layout файла {entry['name']}",
                    entity_type=EntityType.layout,
                    data={"dxf_path": entry["dxf"]},
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
                    layer_entity = Entity(
                        parent_id=layout_entity.id,
                        name=str(layer_name),
                        description=f"Layer layout {layout['name']}",
                        entity_type=EntityType.layer,
                        data={"layout": layout["name"], "dxf_path": entry["dxf"]},
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
                    created_entities += 1

            for block in summary["blocks"]:
                block_data: dict[str, object] = {
                    "entity_count": block["entity_count"],
                    "dxf_path": entry["dxf"],
                }
                if block.get("is_table"):
                    block_data["table"] = block["table"]

                block_entity = Entity(
                    parent_id=file_entity.id,
                    name=str(block["name"]),
                    description=f"Block файла {entry['name']}",
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
                created_entities += 1

            for primitive in summary["primitives"]:
                primitive_entity = Entity(
                    parent_id=file_entity.id,
                    name=str(primitive["type"]),
                    description=str(primitive["text"]),
                    entity_type=EntityType.primitive,
                    data={
                        "layout": primitive["layout"],
                        "layer": primitive["layer"],
                        "location": primitive["location"],
                        "text": primitive["text"],
                        "dxf_path": entry["dxf"],
                    },
                    start_from=source_ref,
                )
                session.add(primitive_entity)
                await session.flush()
                session.add(
                    EntityToEntity(
                        src_id=file_entity.id,
                        dst_id=primitive_entity.id,
                        link="contains_primitive",
                    )
                )
                created_entities += 1

            # Фиксируем изменения после полного разбора одного файла.
            await session.commit()

    return created_entities


async def _save_tree_to_db_from_queue(
    root_path: str,
    converted_queue: _QueueLike,
    producer_count: int,
) -> int:
    async with async_session_factory() as session:
        root_entity = Entity(
            name=Path(root_path).name or root_path,
            description=f"Обрабатываемый каталог: {root_path}",
            entity_type=EntityType.folder,
            data={"path": root_path},
            start_from=root_path,
        )
        session.add(root_entity)
        await session.flush()

        zip_entities: dict[str, Entity] = {}
        created_entities = 1
        completed_producers = 0

        while completed_producers < producer_count:
            queue_item = converted_queue.get()
            event_type = _queue_event_type(queue_item)
            if event_type == _QUEUE_EVENT_DONE:
                completed_producers += 1
                continue
            if event_type == _QUEUE_EVENT_ERROR:
                message = "Неизвестная ошибка конвертации"
                if isinstance(queue_item, dict):
                    message = str(queue_item.get("message", message))
                raise RuntimeError(message)

            entry = cast(ManifestEntry, queue_item)
            source_ref = entry["source_ref"]
            file_type = EntityType.file if entry["kind"] == "file" else EntityType.zipped_file

            parent_entity = root_entity
            if entry["kind"] == "zipped_file":
                zip_source = entry["source"]
                zip_entity = zip_entities.get(zip_source)
                if zip_entity is None:
                    zip_entity = Entity(
                        parent_id=root_entity.id,
                        name=Path(zip_source).name,
                        description=f"ZIP-архив: {zip_source}",
                        entity_type=EntityType.zipfile,
                        data={"path": zip_source},
                        start_from=zip_source,
                    )
                    session.add(zip_entity)
                    await session.flush()
                    session.add(
                        EntityToEntity(
                            src_id=root_entity.id,
                            dst_id=zip_entity.id,
                            link="contains_zip",
                        )
                    )
                    zip_entities[zip_source] = zip_entity
                    created_entities += 1
                parent_entity = zip_entity

            file_entity = Entity(
                parent_id=parent_entity.id,
                name=entry["name"],
                description=f"Исходный файл: {source_ref}",
                entity_type=file_type,
                data={"source_ref": source_ref, "dxf_path": entry["dxf"]},
                file_md5=entry.get("file_md5"),
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

            summary = collect_dxf_summary(Path(entry["dxf"]))
            for layout in summary["layouts"]:
                layout_entity = Entity(
                    parent_id=file_entity.id,
                    name=str(layout["name"]),
                    description=f"Layout файла {entry['name']}",
                    entity_type=EntityType.layout,
                    data={"dxf_path": entry["dxf"]},
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
                    layer_entity = Entity(
                        parent_id=layout_entity.id,
                        name=str(layer_name),
                        description=f"Layer layout {layout['name']}",
                        entity_type=EntityType.layer,
                        data={"layout": layout["name"], "dxf_path": entry["dxf"]},
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
                    created_entities += 1

            for block in summary["blocks"]:
                block_data: dict[str, object] = {
                    "entity_count": block["entity_count"],
                    "dxf_path": entry["dxf"],
                }
                if block.get("is_table"):
                    block_data["table"] = block["table"]

                block_entity = Entity(
                    parent_id=file_entity.id,
                    name=str(block["name"]),
                    description=f"Block файла {entry['name']}",
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
                created_entities += 1

            for primitive in summary["primitives"]:
                primitive_entity = Entity(
                    parent_id=file_entity.id,
                    name=str(primitive["type"]),
                    description=str(primitive["text"]),
                    entity_type=EntityType.primitive,
                    data={
                        "layout": primitive["layout"],
                        "layer": primitive["layer"],
                        "location": primitive["location"],
                        "text": primitive["text"],
                        "dxf_path": entry["dxf"],
                    },
                    start_from=source_ref,
                )
                session.add(primitive_entity)
                await session.flush()
                session.add(
                    EntityToEntity(
                        src_id=file_entity.id,
                        dst_id=primitive_entity.id,
                        link="contains_primitive",
                    )
                )
                created_entities += 1

            # Фиксируем изменения после полного разбора одного файла.
            await session.commit()

    return created_entities


def _ingest_manifest_to_db(
    converted_queue: _QueueLike,
    root_path: str,
    producer_count: int,
) -> int:
    return asyncio.run(_save_tree_to_db_from_queue(root_path, converted_queue, producer_count))


def run_dwg_tree_ingest(
    source_path: Path, 
    conversion_workers: int = 2
) -> dict[str, object]:
    """
    Обходит каталог с DWG-файлами (включая ZIP), конвертирует их в DXF, 
    сохраняет структуру в БД и возвращает статистику.
    """

    entries = discover_dwg_sources(source_path)
    if not entries:
        raise ValueError(f"В каталоге {source_path} не найдено DWG-файлов (включая ZIP).")

    manifest_path = _write_temp_json_file(entries, prefix="parsedwg-dwg-manifest-")
    logger.info("Временный список DWG сохранен: %s", manifest_path)

    effective_workers = _resolve_conversion_workers(conversion_workers)
    converted_dir = Path(tempfile.mkdtemp(prefix="parsedwg-dxf-cache-"))
    batches = _split_to_batches(entries, workers=effective_workers)

    converted_entries: list[ManifestEntry] = []
    with mp.Manager() as manager:
        converted_queue = manager.Queue()

        with ProcessPoolExecutor(max_workers=max(2, effective_workers + 1)) as executor:
            ingest_future = executor.submit(
                _ingest_manifest_to_db,
                converted_queue,
                str(source_path),
                len(batches),
            )
            futures = [
                executor.submit(_convert_batch, batch, str(converted_dir), converted_queue)
                for batch in batches
            ]
            for future in futures:
                converted_entries.extend(future.result())

            created_entities = ingest_future.result()

    converted_entries.sort(key=lambda item: item["source_ref"])
    converted_manifest_path = _write_temp_json_file(
        converted_entries,
        prefix="parsedwg-converted-dxf-",
    )
    logger.info("Временный список DXF сохранен: %s", converted_manifest_path)

    return {
        "manifest": str(manifest_path),
        "converted_manifest": str(converted_manifest_path),
        "dwg_count": len(entries),
        "dxf_count": len(converted_entries),
        "conversion_workers": effective_workers,
        "created_entities": created_entities,
    }


__all__ = ["run_dwg_tree_ingest"]