"""Обход каталога DWG/DXF и сохранение дерева сущностей в БД."""

from __future__ import annotations

from typing import Any, Generator, Protocol, Callable, Iterator, cast

import asyncio
import hashlib
import logging
import sys
import tempfile
import zipfile

from pathlib import Path

from ezdxf.document import Drawing
from ezdxf.layouts.blocklayout import BlockLayout
from ezdxf.addons.odafc import readfile as read_odafc
from ezdxf.filemanagement import readfile
from sqlalchemy import func, select

from .db import async_session_factory
from .orm import Entity, EntityToEntity, EntityType, Project
from .table_analysis import TextClusterAnalyzer
from .dxf_analyzer import DXFAnalyzer

try:
    from tqdm.auto import tqdm as _tqdm
except ImportError:
    def _tqdm(iterable, **kwargs):
        _ = kwargs
        return iterable

logger = logging.getLogger(__name__)

type JobEntry = dict[str, str]
type ProcessedEntry = dict[str, object]
type NameTagsAIConfig = dict[str, str]


class NameTagsExtractor(Protocol):
    def extract(self, text: str) -> list[str]: ...


def skip_blocks(
    block_entity: object,
    filter_handler: Callable[[object], bool] | None = None,
) -> bool:
    """Признак того, какие блоки надо пропускать."""

    if filter_handler is None:
        return False
    return filter_handler(block_entity)


class DWGTreeProcessor:
    """Обходит каталог и собирает задания на разбор DWG/DXF."""

    def __init__(self, source_path: Path, root_path: Path | None = None):
        self.source_path = source_path
        self.root_path = root_path or source_path
        if not self.root_path.exists():
            raise FileNotFoundError(f"Путь {self.root_path} не найден.")

    @staticmethod
    def file_md5(path: Path) -> str:
        """Возвращает MD5-хеш файла для идентификации его содержимого."""

        digest = hashlib.md5(usedforsecurity=False)
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def walk(self, root_path: Path) -> Generator[JobEntry, None, None]:
        """Обходит каталог и генерирует задания на разбор DWG/DXF файлов."""

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

    @staticmethod
    def split_to_batches(entries: list[JobEntry], workers: int) -> list[list[JobEntry]]:
        """Разбивает список заданий на батчи для параллельной обработки."""

        normalized_workers = max(1, workers)
        batches: list[list[JobEntry]] = [[] for _ in range(normalized_workers)]
        for index, entry in enumerate(entries):
            batches[index % normalized_workers].append(entry)
        return [batch for batch in batches if batch]

    @staticmethod
    def extract_from_zip(zip_path: Path, member: str, temp_dir: Path) -> Path:
        """Извлекает файл из ZIP-архива во временную папку и возвращает путь к нему."""

        target_path = temp_dir / Path(member).name
        with zipfile.ZipFile(zip_path) as archive:
            data = archive.read(member)
        target_path.write_bytes(data)
        return target_path

    @staticmethod
    def read_drawing(path: Path):
        """Читает DWG/DXF-файл с помощью ezdxf / ODAFC (для DWG) и возвращает объект Drawing."""

        suffix = path.suffix.lower()
        if suffix == ".dwg":
            return read_odafc(path, "ACAD2018")
        return readfile(path)


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


def iter_blocks(drawing: Drawing) -> Iterator[BlockLayout]:
    """Итерирует блоки в документе с отображением прогресса."""

    logger.debug("Step 1")
    blocks = list(drawing.blocks)
    return iter(
        _tqdm(
            blocks,
            total=len(blocks),
            desc="Blocks",
            unit="block",
            disable=not sys.stderr.isatty(),
        )
    )


def _collect_layout_insert_primitives(doc) -> list[dict[str, object]]:
    primitives: list[dict[str, object]] = []

    for layout in doc.layouts:
        layout_name = str(layout.name)
        for entity in layout:
            if entity.dxftype() != "INSERT" or not entity.dxf.hasattr("name"):
                continue

            target_block = str(entity.dxf.name)
            if skip_blocks(entity):
                continue

            location = ""
            if entity.dxf.hasattr("insert"):
                point = DXFAnalyzer.format_point(getattr(entity.dxf, "insert"))
                if point is not None:
                    location = str(point)

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
    primitives: list[dict[str, object]],
    name_tags_extractor: NameTagsExtractor,
) -> list[dict[str, object]]:
    enriched: list[dict[str, object]] = []
    for primitive in primitives:
        payload: dict[str, object] = dict(primitive)
        if primitive.get("type") not in {"TEXT", "MTEXT"}:
            enriched.append(payload)
            continue

        text = str(primitive.get("text", "")).strip()
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
    primitives: list[dict[str, object]] = []
    for block in iter_blocks(drawing):
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

        for entity in block:
            primitives.append(DXFAnalyzer.get_entity_data(entity, block=block))

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
    doc = DWGTreeProcessor.read_drawing(drawing_path)
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
            
            working_path = DWGTreeProcessor.extract_from_zip(source, member_name, temp_dir)
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
    name_tags_config: NameTagsAIConfig | None = None,
) -> list[ProcessedEntry]:
    """Последовательно обрабатывает набор файлов и возвращает готовые summaries."""

    processed: list[ProcessedEntry] = []

    name_tags_extractor = _build_name_tags_extractor_from_config(name_tags_config)
    for entry in batch:
        processed.append(process_entry(entry, name_tags_extractor=name_tags_extractor))

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
        project_id=project_id,

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
        )
        session.add(folder_entity)
        await session.flush()
        # session.add(
        #     EntityToEntity(
        #         src_id=parent_entity.id,
        #         dst_id=folder_entity.id,
        #         link="contains_folder",
        #     )
        # )
        folders[rel] = folder_entity
        created += 1

    return folders, created


async def save_tree_to_db(
    root_path: str,
    processed_entries: list[ProcessedEntry],
    project_name: str,
    project_description: str | None = None,
    created_by: str | None = None,
) -> tuple[str, int]:
    """Сохраняет дерево сущностей в БД по уже обработанным файлам.
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

        for entry in processed_entries:
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
                    )
                    session.add(zip_entity)
                    await session.flush()
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
            )
            session.add(file_entity)
            await session.flush()
            created_entities += 1

            summary = cast(dict[str, list[dict[str, object]]], entry["summary"])
            layer_entities_by_key: dict[tuple[str, str], Entity] = {}
            for layout in summary["layouts"]:
                layout_name = str(layout["name"])
                layout_entity = Entity(
                    parent_id=file_entity.id,
                    file_id=file_entity.id,
                    project_id=project_id,
                    name=layout_name,
                    description=f"Layout файла {entry['name']}",
                    entity_text=_build_entity_text(f"Layout файла {entry['name']}"),
                    entity_type=EntityType.layout,
                    data={},
                )
                session.add(layout_entity)
                await session.flush()
                created_entities += 1

                for layer_name in cast(list[str], layout["layers"]):
                    layer_name_str = str(layer_name)
                    layer_entity = Entity(
                        parent_id=layout_entity.id,
                        file_id=file_entity.id,
                        project_id=project_id,
                        name=layer_name_str,
                        description=f"Layer layout {layout_name}",
                        entity_text=_build_entity_text(f"Layer layout {layout_name}"),
                        entity_type=EntityType.layer,
                        data={"layout": layout_name},
                    )
                    session.add(layer_entity)
                    await session.flush()
                    layer_entities_by_key[(layout_name, layer_name_str)] = layer_entity
                    created_entities += 1

            block_entities_by_name: dict[str, Entity] = {}
            for block in summary["blocks"]:
                block_name = str(block["name"])
                if skip_blocks(block_name):
                    continue

                block_data: dict[str, object] = {
                    "entity_count": block["entity_count"],
                }
                if block.get("is_table"):
                    block_data["table"] = block["table"]

                block_entity = Entity(
                    parent_id=file_entity.id,
                    file_id=file_entity.id,
                    project_id=project_id,
                    name=block_name,
                    description=f"Block файла {entry['name']}",
                    entity_text=_build_entity_text(f"Block файла {entry['name']}"),
                    entity_type=EntityType.block,
                    data=block_data,
                    is_table=cast(bool, block["is_table"]),
                )
                session.add(block_entity)
                await session.flush()
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

                primitive_entity = Entity(
                    parent_id=parent_block_entity.id,
                    file_id=file_entity.id,
                    project_id=project_id,
                    name=str(primitive.get("type", "")),
                    description=str(primitive.get("text", "")),
                    entity_text=_build_entity_text(str(primitive.get("text", ""))),
                    entity_type=str(primitive.get("type", "primitive")),
                    data=primitive,
                    geom=primitive.get("geom", None)
                )
                session.add(primitive_entity)
                await session.flush()

                layout_name = primitive.get("layout")
                layer_name = primitive.get("layer")
                if isinstance(layout_name, str) and isinstance(layer_name, str):
                    layer_entity = layer_entities_by_key.get((layout_name, layer_name))
                    if layer_entity is not None:
                        session.add(
                            EntityToEntity(
                                dst_id=layer_entity.id,
                                src_id=primitive_entity.id,
                                link="on_layer",
                            )
                        )

                created_entities += 1

            await session.commit()

    return str(project_id), created_entities


def run_process_tree(
    source_path: Path,
    project_name: str | None = None,
    project_description: str | None = None,
    created_by: str | None = None,
    name_tags_config: NameTagsAIConfig | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """Обходит каталог/файл, разбирает DWG/DXF последовательно и сохраняет дерево в БД."""

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

    processed_entries = process_batch(entries, name_tags_config=name_tags_config)

    project_id: str | None = None
    created_entities = 0
    if dry_run:
        project_id, created_entities = None, 0
    else:
        project_id, created_entities = asyncio.run(
            save_tree_to_db(
                root_path=str(root_path),
                processed_entries=processed_entries,
                project_name=project_name or root_path.name or str(root_path),
                project_description=project_description,
                created_by=created_by,
            )
        )

    processed_entries.sort(key=lambda item: str(item.get("source_ref", "")))
    logger.info(
        "Обработка завершена: files=%d",
        len(processed_entries),
    )

    mode = "direct"

    return {
        "job_id": None,
        "project_id": project_id,
        "file_count": len(entries),
        "processed_count": len(processed_entries),
        "workers": 1,
        "mode": mode,
        "dry_run": dry_run,
        "created_entities": created_entities,
    }


__all__ = ["DWGTreeProcessor", "collect_dxf_summary", "run_process_tree"]
