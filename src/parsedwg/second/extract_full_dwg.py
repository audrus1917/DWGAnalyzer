"""
Полное извлечение содержимого DWG/DXF файла в БД (таблицы dwg_*).
DWG автоматически конвертируется через ODA File Converter.

Usage:
    PYTHONPATH=src python scripts/extract_full_dwg.py path/to/file.dwg
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any
from uuid import UUID

from ezdxf.addons.odafc import readfile as read_odafc
from ezdxf.document import Drawing
from ezdxf.filemanagement import readfile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from parsedwg.settings import settings


engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def file_md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def open_drawing(path: Path) -> Drawing:
    if path.suffix.lower() == ".dwg":
        print("  Конвертация DWG → DXF через ODA...")
        return read_odafc(path, "ACAD2018")
    return readfile(str(path))


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def serialize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool, str)):
        return value
    if hasattr(value, "x") and hasattr(value, "y"):
        result = {"x": float(value.x), "y": float(value.y)}
        if hasattr(value, "z"):
            result["z"] = float(value.z)
        return result
    if isinstance(value, (list, tuple)):
        return [serialize_value(v) for v in value]
    return str(value)


def collect_dxf_data(entity) -> dict[str, Any]:
    data: dict[str, Any] = {}
    try:
        for attr_name, value in entity.dxf.all_existing_dxf_attribs().items():
            try:
                data[attr_name] = serialize_value(value)
            except Exception:
                data[attr_name] = str(value)
    except Exception:
        pass
    return data


def get_insert_point(entity) -> tuple[float | None, float | None, float | None]:
    for attr in ("insert", "start"):
        if entity.dxf.hasattr(attr):
            pt = getattr(entity.dxf, attr)
            return (
                safe_float(getattr(pt, "x", None)),
                safe_float(getattr(pt, "y", None)),
                safe_float(getattr(pt, "z", None)),
            )
    return None, None, None


def get_text_value(entity) -> str | None:
    etype = entity.dxftype()
    try:
        if etype in ("TEXT", "ATTDEF", "ATTRIB"):
            return str(entity.dxf.text).strip() or None
        if etype == "MTEXT":
            plain = getattr(entity, "plain_text", None)
            if callable(plain):
                return plain().strip() or None
    except Exception:
        pass
    return None


async def extract(path: Path) -> None:
    doc = open_drawing(path)
    md5 = file_md5(path)
    dxf_version = doc.dxfversion

    async with AsyncSessionFactory() as session:
        # --- dwg_file ---
        row = await session.execute(
            text("INSERT INTO dwg_file (path, md5, dxf_version) VALUES (:p, :m, :v) RETURNING id"),
            {"p": str(path), "m": md5, "v": dxf_version},
        )
        file_id: UUID = row.scalar_one()
        print(f"  dwg_file: {file_id}")

        # --- dwg_layer ---
        layer_name_to_id: dict[str, UUID] = {}
        layer_rows = []
        for layer in doc.layers:
            name = str(layer.dxf.name)
            lid = uuid.uuid4()
            layer_name_to_id[name] = lid
            layer_rows.append({
                "id": lid,
                "fid": file_id,
                "name": name,
                "color": safe_float(layer.dxf.get("color", None)),
                "lt": str(layer.dxf.get("linetype", "")) or None,
                "lw": safe_float(layer.dxf.get("lineweight", None)),
                "on": not layer.is_off(),
                "frozen": layer.is_frozen(),
                "locked": layer.is_locked(),
            })
        if layer_rows:
            await session.execute(
                text("""
                    INSERT INTO dwg_layer (id, file_id, name, color, linetype, lineweight, is_on, is_frozen, is_locked)
                    VALUES (:id, :fid, :name, :color, :lt, :lw, :on, :frozen, :locked)
                """),
                layer_rows,
            )
        print(f"  dwg_layer: {len(layer_rows)}")

        # --- dwg_block_def ---
        layout_block_names = {layout.block_record_name for layout in doc.layouts}
        block_name_to_id: dict[str, UUID] = {}
        block_rows = []
        for block in doc.blocks:
            name = str(block.name)
            bid = uuid.uuid4()
            block_name_to_id[name] = bid
            bp = block.block.dxf.base_point if block.block else None
            block_rows.append({
                "id": bid,
                "fid": file_id,
                "name": name,
                "ilb": name in layout_block_names,
                "bx": safe_float(getattr(bp, "x", None)) if bp else None,
                "by": safe_float(getattr(bp, "y", None)) if bp else None,
                "bz": safe_float(getattr(bp, "z", None)) if bp else None,
            })
        if block_rows:
            await session.execute(
                text("""
                    INSERT INTO dwg_block_def (id, file_id, name, is_layout_block, base_x, base_y, base_z)
                    VALUES (:id, :fid, :name, :ilb, :bx, :by, :bz)
                """),
                block_rows,
            )
        print(f"  dwg_block_def: {len(block_rows)}")

        # --- dwg_layout ---
        layout_rows = []
        for layout in doc.layouts:
            block_def_id = block_name_to_id.get(layout.block_record_name)
            if block_def_id is None:
                continue
            layout_rows.append({
                "fid": file_id,
                "bid": block_def_id,
                "name": str(layout.name),
                "ms": layout.is_modelspace,
                "tab": safe_float(layout.dxf.get("taborder", None)),
            })
        if layout_rows:
            await session.execute(
                text("""
                    INSERT INTO dwg_layout (file_id, block_def_id, name, is_modelspace, tab_order)
                    VALUES (:fid, :bid, :name, :ms, :tab)
                """),
                layout_rows,
            )
        print(f"  dwg_layout: {len(layout_rows)}")

        # --- Сбор dwg_entity + dwg_attrib ---
        entity_rows = []
        attrib_rows = []

        for block in doc.blocks:
            block_name = str(block.name)
            block_def_id = block_name_to_id.get(block_name)
            if block_def_id is None:
                continue

            for entity in block:
                etype = entity.dxftype()
                layer_name = str(getattr(entity.dxf, "layer", "")) or None
                layer_id = layer_name_to_id.get(layer_name) if layer_name else None
                ix, iy, iz = get_insert_point(entity)
                handle = str(entity.dxf.handle) if entity.dxf.hasattr("handle") else None
                text_val = get_text_value(entity)
                dxf_data = collect_dxf_data(entity)

                ref_block_def_id: UUID | None = None
                if etype == "INSERT" and entity.dxf.hasattr("name"):
                    ref_block_def_id = block_name_to_id.get(str(entity.dxf.name))

                entity_id = uuid.uuid4()
                entity_rows.append({
                    "id": entity_id,
                    "fid": file_id,
                    "bid": block_def_id,
                    "lid": layer_id,
                    "etype": etype,
                    "handle": handle,
                    "ix": ix, "iy": iy, "iz": iz,
                    "rbid": ref_block_def_id,
                    "tv": text_val,
                    "data": json.dumps(dxf_data),
                })

                if etype == "INSERT":
                    try:
                        for attrib in entity.attribs:
                            aix, aiy, aiz = get_insert_point(attrib)
                            attrib_rows.append({
                                "fid": file_id,
                                "eid": entity_id,
                                "tag": str(attrib.dxf.tag),
                                "val": str(attrib.dxf.text).strip() or None,
                                "vis": bool(attrib.dxf.get("invisible", 0)) is False,
                                "ix": aix, "iy": aiy, "iz": aiz,
                                "data": json.dumps(collect_dxf_data(attrib)),
                            })
                    except Exception as e:
                        print(f"    [warn] attrib error in {block_name}/{handle}: {e}")

        print(f"  Собрано: entity={len(entity_rows)}, attrib={len(attrib_rows)}")
        print("  Вставка в БД...")

        if entity_rows:
            await session.execute(
                text("""
                    INSERT INTO dwg_entity
                        (id, file_id, block_def_id, layer_id, entity_type, handle,
                         insert_x, insert_y, insert_z, ref_block_def_id,
                         text_value, dxf_data)
                    VALUES
                        (:id, :fid, :bid, :lid, :etype, :handle,
                         :ix, :iy, :iz, :rbid,
                         :tv, CAST(:data AS jsonb))
                """),
                entity_rows,
            )

        if attrib_rows:
            await session.execute(
                text("""
                    INSERT INTO dwg_attrib
                        (file_id, entity_id, tag, value, is_visible, insert_x, insert_y, insert_z, dxf_data)
                    VALUES
                        (:fid, :eid, :tag, :val, :vis, :ix, :iy, :iz, CAST(:data AS jsonb))
                """),
                attrib_rows,
            )

        await session.commit()
        print(f"  dwg_entity: {len(entity_rows)}")
        print(f"  dwg_attrib: {len(attrib_rows)}")
        print(f"  Готово. file_id={file_id}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/extract_full_dwg.py path/to/file.dwg")
        sys.exit(1)

    path = Path(sys.argv[1]).expanduser().resolve()
    if not path.exists():
        print(f"Файл не найден: {path}")
        sys.exit(1)

    print(f"Извлечение: {path}")
    asyncio.run(extract(path))


if __name__ == "__main__":
    main()
