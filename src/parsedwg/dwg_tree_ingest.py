from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import tempfile
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ezdxf.filemanagement import readfile

from .db import async_session_factory
from .orm import Entity, EntityToEntity, EntityType
from .parsers import _convert_dwg_to_dxf

logger = logging.getLogger(__name__)

type ManifestEntry = dict[str, str]


def _discover_dwg_sources(root_path: Path) -> list[ManifestEntry]:
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

        converted_temp_path = _convert_dwg_to_dxf(working_dwg)
        target_name = hashlib.sha1(source_ref.encode("utf-8")).hexdigest() + ".dxf"
        target_path = converted_root / target_name
        target_path.write_bytes(converted_temp_path.read_bytes())

    converted_entry: ManifestEntry = {
        **entry,
        "source_ref": source_ref,
        "dxf": str(target_path),
    }
    return converted_entry


def _convert_batch(batch: list[ManifestEntry], converted_dir: str) -> list[ManifestEntry]:
    converted: list[ManifestEntry] = []
    for entry in batch:
        converted.append(_convert_entry(entry, converted_dir))
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
        layers.update(_collect_entity_layers(doc, entity))
    return sorted(layers)


def _collect_dxf_summary(dxf_path: Path) -> dict[str, object]:
    doc = readfile(str(dxf_path))
    layouts: list[dict[str, object]] = []
    for layout in doc.layouts:
        layers = _collect_layout_layers(doc, layout)
        layouts.append({"name": layout.name, "layers": layers})

    blocks = [
        {
            "name": block.name,
            "entity_count": sum(1 for _ in block),
        }
        for block in doc.blocks
    ]
    return {"layouts": layouts, "blocks": blocks}


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

            summary = _collect_dxf_summary(Path(entry["dxf"]))
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

                for layer_name in layout["layers"]:
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
                block_entity = Entity(
                    parent_id=file_entity.id,
                    name=str(block["name"]),
                    description=f"Block файла {entry['name']}",
                    entity_type=EntityType.block,
                    data={"entity_count": block["entity_count"], "dxf_path": entry["dxf"]},
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

        await session.commit()

    return created_entities


def _ingest_manifest_to_db(converted_manifest_path: str, root_path: str) -> int:
    entries = _load_manifest(converted_manifest_path)
    return asyncio.run(_save_tree_to_db(root_path, entries))


def run_dwg_tree_ingest(source_path: Path, conversion_workers: int = 2) -> dict[str, object]:
    entries = _discover_dwg_sources(source_path)
    if not entries:
        raise ValueError(f"В каталоге {source_path} не найдено DWG-файлов (включая ZIP).")

    manifest_path = _write_temp_json_file(entries, prefix="parsedwg-dwg-manifest-")
    logger.info("Временный список DWG сохранен: %s", manifest_path)

    converted_dir = Path(tempfile.mkdtemp(prefix="parsedwg-dxf-cache-"))
    batches = _split_to_batches(entries, workers=conversion_workers)

    converted_entries: list[ManifestEntry] = []
    with ProcessPoolExecutor(max_workers=max(1, conversion_workers)) as executor:
        futures = [executor.submit(_convert_batch, batch, str(converted_dir)) for batch in batches]
        for future in futures:
            converted_entries.extend(future.result())

    converted_entries.sort(key=lambda item: item["source_ref"])
    converted_manifest_path = _write_temp_json_file(
        converted_entries,
        prefix="parsedwg-converted-dxf-",
    )
    logger.info("Временный список DXF сохранен: %s", converted_manifest_path)

    with ProcessPoolExecutor(max_workers=1) as executor:
        created_entities = executor.submit(
            _ingest_manifest_to_db,
            str(converted_manifest_path),
            str(source_path),
        ).result()

    return {
        "manifest": str(manifest_path),
        "converted_manifest": str(converted_manifest_path),
        "dwg_count": len(entries),
        "dxf_count": len(converted_entries),
        "created_entities": created_entities,
    }


__all__ = ["run_dwg_tree_ingest"]