"""Обходит каталоги DWG/DXF и сохраняет дерево сущностей в базу данных."""

from __future__ import annotations

from typing import Any, Generator, Protocol, cast

import hashlib
import logging
import tempfile
import zipfile

from pathlib import Path

from ezdxf.document import Drawing
from ezdxf.addons.odafc import readfile as read_odafc
from ezdxf.filemanagement import readfile
from sqlalchemy import func, select

from .constants import ENTITY_TYPES, EntityType
from .db import session_factory
from .orm import Entity, EntityEmbedding, Primitive, Project
from .dxf_analyzer import DXFAnalyzer
from .utils import safe_float
from src.parsedwg.table_analysis import TextClusterAnalyzer


logger = logging.getLogger(__name__)

PRIMITIVE_BATCH_SIZE = 1000
ENTITY_TYPE_ALIASES = {
    "MULTILEADER": "MLEADER",
}

type JobEntry = dict[str, str]
type ProcessedEntry = dict[str, object]
type NameTagsAIConfig = dict[str, str]


class NameTagsExtractor(Protocol):
    def extract(self, text: str) -> list[str]: ...


class DWGTreeProcessor:
    """Обходит каталог и собирает задания на обработку DWG/DXF."""

    def __init__(self, source_path: Path, root_path: Path | None = None):
        self.source_path = source_path
        self.root_path = root_path or source_path
        if not self.root_path.exists():
            raise FileNotFoundError(f"Путь {self.root_path} не найден.")

    @staticmethod
    def file_md5(path: Path) -> str:
        """Возвращает MD5-хэш файла для идентификации содержимого."""

        digest = hashlib.md5(usedforsecurity=False)
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def walk(self, sources_path: Path) -> Generator[JobEntry, None, None]:
        """Обходит каталог и выдаёт задания на разбор DWG/DXF."""

        for file_path in sorted(path for path in sources_path.rglob("*") if path.is_file()):
            suffix = file_path.suffix.lower()
            if suffix in {".dwg", ".dxf", ".dxb"}:
                parent_rel = file_path.parent.relative_to(sources_path)
                parent_rel_str = "" if str(parent_rel) == "." else parent_rel.as_posix()
                yield {
                    "kind": "file",
                    "root": str(sources_path),
                    "source": str(file_path),
                    "name": file_path.name,
                    "file_type": suffix,
                    "parent_rel": parent_rel_str,
                }
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
                        yield {
                            "kind": "zipped_file",
                            "root": str(sources_path),
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
        """Разбивает задания на пачки для параллельной обработки."""

        normalized_workers = max(1, workers)
        batches: list[list[JobEntry]] = [[] for _ in range(normalized_workers)]
        for index, entry in enumerate(entries):
            batches[index % normalized_workers].append(entry)
        return [batch for batch in batches if batch]

    @staticmethod
    def extract_from_zip(zip_path: Path, member: str, temp_dir: Path) -> Path:
        """Извлекает файл из ZIP-архива во временный каталог и возвращает его путь."""

        target_path = temp_dir / Path(member).name
        with zipfile.ZipFile(zip_path) as archive:
            data = archive.read(member)
        target_path.write_bytes(data)
        return target_path

    @staticmethod
    def read_drawing(path: Path):
        """Читает DWG/DXF-файл через ezdxf или ODAFC и возвращает Drawing."""

        suffix = path.suffix.lower()
        if suffix == ".dwg":
            return read_odafc(path, "ACAD2018")
        return readfile(path)


def _build_entity_text(text_value: str | None):
    if text_value is None or not text_value.strip():
        return None
    return func.to_tsvector("russian", text_value)


def _build_entity_embedding(text_value: str | None) -> EntityEmbedding | None:
    entity_text = _build_entity_text(text_value)
    if entity_text is None:
        return None
    return EntityEmbedding(entity_text=entity_text)


def _coerce_entity_type(value: object) -> EntityType:
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


def iter_blocks(drawing: Drawing) -> list[Any]:
    """Итерирует блоки документа с возможностью отображать прогресс."""

    return list(drawing.blocks)


def _is_layout_block(block) -> bool:
    block_name = block.name.lower()
    return block_name.startswith("*model_space") or block_name.startswith("*paper_space")


def collect_layout_entities(doc) -> Generator[dict[str, Any] | None, None, None]:
    """Итерирует все сущности во всех layout и возвращает их данные."""

    for layout in doc.layouts:
        logger.debug(f"Обрабатываем layout: {layout.name}, количество сущностей: {len(layout)}")
        for dxf_entity in layout:
            yield DXFAnalyzer.get_entity_data(
                dxf_entity, 
                parent=layout,
                layout=layout
            )


def collect_drawing_summary(drawing: Drawing) -> dict[str, Any]:
    """Собирает данные layout, блоков и примитивов из чертежа."""

    # Предварительный вывод статистики
    logger.debug(f"Количество layout'ов: {len(drawing.layouts)}")
    logger.debug(f"Количество блоков: {len(drawing.blocks)}")
    logger.debug(f"Количество слоев: {len(drawing.layers)}")
    total_primitives: int = 0
    for laout in drawing.layouts:
        total_primitives += len(laout)
    logger.debug(f"Количество примитивов в layout'ах: {total_primitives}")

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
    primitives: list[dict[str, object]] = []
    for block in iter_blocks(drawing):
        if _is_layout_block(block):
            continue

        table_stats = TextClusterAnalyzer.analyze_table(block)
        block_description = DXFAnalyzer.get_block_decsription(drawing, block.name)
        blocks.append(
            {
                "name": block.name,
                "entity_count": sum(1 for _ in block),
                "description": block_description or '',
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
            if entity.dxftype() == "INSERT":
                entity_data = DXFAnalyzer.get_entity_data(entity, block)
                if entity_data is not None:
                    primitives.append(entity_data)

    for entity_data in collect_layout_entities(drawing):
        if entity_data is not None:
            primitives.append(entity_data)

    primitives_payload = cast(list[dict[str, object]], primitives)

    return {
        "layouts": layouts,
        "layers": layers,
        "blocks": blocks,
        "primitives": primitives_payload,
    }


def collect_dxf_summary(drawing_path: Path) -> dict[str, Any]:
    """Собирает данные layout, блоков и примитивов из DWG/DXF-файла."""

    # Read the DWG/DXF file.
    doc = DWGTreeProcessor.read_drawing(drawing_path)
    return collect_drawing_summary(doc)


def process_entry(entry: JobEntry) -> ProcessedEntry:
    source = Path(entry["source"])

    with tempfile.TemporaryDirectory(prefix="parsedwg-process-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)

        is_zip = ""
        if entry["kind"] == "file":
            source_ref = entry["source"]
            working_path = source
            entity_md5 = DWGTreeProcessor.file_md5(working_path)
        else:
            is_zip = " (zip)"
            member_name = entry.get("member")
            if member_name is None:
                raise ValueError("Для zipped_file не указан member.")

            working_path = DWGTreeProcessor.extract_from_zip(source, member_name, temp_dir)
            source_ref = f"{entry['source']}::{member_name}"
            entity_md5 = DWGTreeProcessor.file_md5(working_path)

        logger.info("Обрабатываем файл: %s%s", source_ref, is_zip)
        summary = collect_dxf_summary(working_path)

    processed_entry: ProcessedEntry = {
        **entry,
        "source_ref": source_ref,
        "entity_md5": entity_md5,
        "summary": summary,
    }
    return processed_entry


def process_batch(batch: list[JobEntry]) -> Generator[ProcessedEntry, None, None]:
    """Последовательно обрабатывает пачку файлов и возвращает готовые сводки."""

    for entry in batch:
        yield process_entry(entry)


def create_folders_tree(
    session,
    root_path: Path,
    project_id,
) -> tuple[dict[str, Entity], int]:
    root_entity = Entity(
        name=root_path.name or str(root_path),
        description=f"Источник сканирования: {root_path}",
        entity_type=EntityType.FOLDER,
        data={"path": str(root_path)},
        project_id=project_id,
        embedding_data=_build_entity_embedding(f"Источник сканирования: {root_path}"),
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
            description=f"Каталог: {dir_path}",
            entity_type=EntityType.FOLDER,
            data={"path": str(dir_path)},
            embedding_data=_build_entity_embedding(f"Каталог: {dir_path}"),
        )
        session.add(folder_entity)
        session.flush()
        folders[rel] = folder_entity
        created += 1

    return folders, created


def flush_primitives_batch(
    session,
    primitive_batch: list[Primitive],
    processed_count: int,
    primitives_total: int,
    final: bool = False,
) -> int:
    if not primitive_batch:
        return 0

    if final:
        logger.info(
            "Сохраняем финальную пачку примитивов: %d / %d",
            processed_count,
            primitives_total,
        )
    else:
        logger.info(
            "Сохраняем пачку примитивов: %d / %d",
            processed_count,
            primitives_total,
        )

    session.add_all(primitive_batch)
    session.flush()

    created_count = len(primitive_batch)
    session.commit()
    primitive_batch.clear()
    return created_count


def drawing_to_db(
    sources_path: str | Path,
    processed_entries: Generator[ProcessedEntry, None, None],
    project_id: int,
) -> int:
    """Сохраняет дерево сущностей в базу данных по уже обработанным файлам.

    Возвращает количество созданных сущностей.
    """

    logger.info("Сохраняем результаты в БД")
    with session_factory() as session:

        root = Path(sources_path)
        folders, created_entities = create_folders_tree(session, root, project_id)

        zip_entities: dict[str, Entity] = {}

        for entry in processed_entries:
            source_ref = str(entry["source_ref"])
            kind = str(entry["kind"])
            logger.info("Сохраняем для файла для сохранения: %s (%s)", source_ref, kind)
            file_type = EntityType.FILE if kind == "file" else EntityType.ZIPPED_FILE

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
                        entity_type=EntityType.ZIPFILE,
                        data={"path": zip_source},
                        embedding_data=_build_entity_embedding(f"ZIP-архив: {zip_source}"),
                    )
                    session.add(zip_entity)
                    session.flush()
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
                entity_type=file_type,
                data={"source_ref": source_ref},
                entity_md5=str(entry.get("entity_md5", "")) or None,
                embedding_data=_build_entity_embedding(f"Исходный файл: {source_ref}"),
            )
            session.add(file_entity)
            session.flush()
            created_entities += 1

            summary = cast(dict[str, list[dict[str, object]]], entry["summary"])
            layer_entities_by_key: dict[str, Entity] = {}
            layout_entities_by_name: dict[str, int] = {}
            logger.info("Layouts (%d шт.)", len(summary.get("layouts", [])))
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
                    embedding_data=_build_entity_embedding(f"Layout {entry['name']}"),
                )
                session.add(layout_entity)
                session.flush()
                layout_entities_by_name[layout_name] = layout_entity.id
                created_entities += 1

            logger.info("Слои (%d шт.)", len(summary.get("layers", [])))
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
                    embedding_data=_build_entity_embedding(f"Layer {layer_name}"),
                )
                session.add(layer_entity)
                session.flush()
                layer_entities_by_key[layer_name] = layer_entity
                created_entities += 1

            block_entities_by_name: dict[str, int] = {}
            logger.info("Блоки (%d шт.)", len(summary.get("blocks", [])))
            for block in summary["blocks"]:
                block_name = str(block["name"])

                block_data: dict[str, object] = {
                    "entity_count": block["entity_count"],
                }
                if block.get("is_table"):
                    block_data["table"] = block["table"]

                block_description = block.get("description")

                block_entity = Entity(
                    parent_id=file_entity.id,
                    file_id=file_entity.id,
                    project_id=project_id,
                    name=block_name,
                    description=str(block_description),
                    entity_type=EntityType.BLOCK,
                    data=block_data,
                    is_table=bool(block.get("is_table")),
                    embedding_data=_build_entity_embedding(f"Block {block_name}"),
                )
                session.add(block_entity)
                session.flush()
                block_entities_by_name[block_name] = block_entity.id
                created_entities += 1

            primitives = summary.get("primitives", [])
            primitive_batch: list[Primitive] = []

            logger.info("Примитивы (%d шт.)", len(primitives))
            primitive_iterable = primitives

            for idx, primitive in enumerate(primitive_iterable, start=1):
                primitive_payload = dict(primitive)

                block_name = str(primitive_payload["block"])

                parent_block_name = str(primitive_payload.get("parent_block", block_name))

                parent_block_entity_id = (
                    block_entities_by_name.get(parent_block_name)
                    or layout_entities_by_name.get(parent_block_name)
                )
                if parent_block_entity_id is None:
                    logger.warning(
                        "Пропускаем примитив %s: не найден parent entity %s",
                        primitive.get("text", ""),
                        block_name,
                    )
                    if idx % PRIMITIVE_BATCH_SIZE == 0:
                        created_entities += flush_primitives_batch(
                            session,
                            primitive_batch,
                            processed_count=idx,
                            primitives_total=len(primitives),
                        )
                    continue

                if "name" in primitive_payload and isinstance(primitive_payload["name"], str):
                    name = str(primitive_payload.pop("name")).strip()
                else:
                    name = str(primitive_payload.get("type", ""))

                geom = primitive_payload.pop("geom", None)
                layer_name = primitive_payload.get("layer")
                layer_entity = (
                    layer_entities_by_key.get(layer_name)
                    if isinstance(layer_name, str)
                    else None
                )
                primitive_entity = Primitive(
                    parent_id=parent_block_entity_id,
                    file_id=file_entity.id,
                    project_id=project_id,
                    layer_id=layer_entity.id if layer_entity is not None else None,
                    name=name,
                    entity_type=_coerce_entity_type(primitive_payload.get("type")),
                    data=primitive_payload,
                    geom=geom if isinstance(geom, str) else None,
                )
                primitive_batch.append(primitive_entity)

                if idx % PRIMITIVE_BATCH_SIZE == 0:
                    created_entities += flush_primitives_batch(
                        session,
                        primitive_batch,
                        processed_count=idx,
                        primitives_total=len(primitives),
                    )

            if primitive_batch:
                created_entities += flush_primitives_batch(
                    session,
                    primitive_batch,
                    processed_count=len(primitives),
                    primitives_total=len(primitives),
                    final=True,
                )
            else:
                session.commit()

    return created_entities


def process_source(
    sources_path: Path,
    project_name: str | None = None,
) -> dict[str, object]:
    """Обходит каталог или файл, разбирает DWG/DXF и сохраняет дерево в БД."""

    logger.info("Старт обработки")

    project_id = None
    with session_factory() as session:
        # Reuse an existing project or create a new one.
        result = session.execute(
            select(Project.id).where(Project.name == project_name)
        )
        project_id = result.scalar_one_or_none()

    if project_id is None:
        raise RuntimeError(f"Проект с именем '{project_name}' не найден.")

    if sources_path.is_file():
        logger.info("Обрабатываем файл: %s", sources_path)
        suffix = sources_path.suffix.lower()
        if suffix not in {".dwg", ".dxf", ".dxb"}:
            raise ValueError("Поддерживаются только файлы DWG, DXF, DXB.")

        drawing_files = [
            {
                "kind": "file",
                "source": str(sources_path),
                "name": sources_path.name,
                "file_type": suffix,
                "parent_rel": "",
            }
        ]
    elif sources_path.is_dir():
        logger.info("Обрабатываем каталог: %s", sources_path)
        drawing_files = list(DWGTreeProcessor(sources_path).walk(sources_path))
        if not drawing_files:
            raise ValueError(
                f"В каталоге {sources_path} не найдено DWG / DXF / DXB-файлов (включая ZIP)."
            )
    else:
        raise ValueError(f"Путь {sources_path} не найден.")

    logger.info("Найдено файлов для обработки: %d", len(drawing_files))

    processed_entries = process_batch(drawing_files)

    created_entities = 0
    created_entities = drawing_to_db(
        sources_path,
        processed_entries,
        project_id=project_id,
    )

    logger.info("Обработка завершена")
    return {
        "job_id": None,
        "project_id": project_id,
        "file_count": len(drawing_files),
        "workers": 1,
        "mode": "direct",
        "created_entities": created_entities,
    }


__all__ = ["DWGTreeProcessor", "collect_dxf_summary", "process_source"]
