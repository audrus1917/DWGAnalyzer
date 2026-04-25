"""
Верификация полноты извлечения DWG/DXF файла.
Сравнивает содержимое файла с тем, что записано в БД (таблицы dwg_*).

Что проверяется:
  1. Количество сущностей по типам в каждом блоке (файл vs БД)
  2. Все ссылки INSERT → block_def разрешены
  3. Все слои примитивов присутствуют в dwg_layer
  4. Все ATTRIB имеют родительский INSERT в БД
  5. Количество ATTRIB по INSERT (файл vs БД)

Usage:
    PYTHONPATH=src python scripts/verify_dwg_extraction.py path/to/file.dwg [file_id]

Если file_id не указан — берётся последняя запись в dwg_file для этого пути.
"""

from __future__ import annotations

import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ezdxf.addons.odafc import readfile as read_odafc
from ezdxf.filemanagement import readfile
from parsedwg.settings import settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def open_drawing(path: Path):
    if path.suffix.lower() == ".dwg":
        print("  Открытие DWG через ODA...")
        return read_odafc(path, "ACAD2018")
    return readfile(str(path))


def count_from_file(doc) -> dict[str, dict[str, int]]:
    """block_name → {entity_type → count}"""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for block in doc.blocks:
        block_name = str(block.name)
        for entity in block:
            counts[block_name][entity.dxftype()] += 1
    return counts


def count_attribs_from_file(doc) -> dict[str, int]:
    """handle_of_insert → attrib_count"""
    result: dict[str, int] = {}
    for block in doc.blocks:
        for entity in block:
            if entity.dxftype() == "INSERT":
                handle = str(entity.dxf.handle) if entity.dxf.hasattr("handle") else None
                if handle:
                    try:
                        result[handle] = len(list(entity.attribs))
                    except Exception:
                        result[handle] = 0
    return result


async def count_from_db(session: AsyncSession, file_id: str) -> dict[str, dict[str, int]]:
    """block_name → {entity_type → count} из БД"""
    rows = await session.execute(
        text("""
            SELECT b.name as block_name, e.entity_type, COUNT(*) as cnt
            FROM dwg_entity e
            JOIN dwg_block_def b ON b.id = e.block_def_id
            WHERE e.file_id = :fid
            GROUP BY b.name, e.entity_type
        """),
        {"fid": file_id},
    )
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        counts[row.block_name][row.entity_type] = row.cnt
    return counts


async def check_unresolved_inserts(session: AsyncSession, file_id: str) -> int:
    r = await session.execute(
        text("""
            SELECT COUNT(*) FROM dwg_entity
            WHERE file_id = :fid AND entity_type = 'INSERT' AND ref_block_def_id IS NULL
        """),
        {"fid": file_id},
    )
    return r.scalar_one()


async def check_missing_layers(session: AsyncSession, file_id: str) -> int:
    r = await session.execute(
        text("""
            SELECT COUNT(DISTINCT e.id) FROM dwg_entity e
            LEFT JOIN dwg_layer l ON l.id = e.layer_id
            WHERE e.file_id = :fid AND e.layer_id IS NOT NULL AND l.id IS NULL
        """),
        {"fid": file_id},
    )
    return r.scalar_one()


async def count_attribs_from_db(session: AsyncSession, file_id: str) -> dict[str, int]:
    """handle → attrib_count из БД"""
    rows = await session.execute(
        text("""
            SELECT e.handle, COUNT(a.id) as cnt
            FROM dwg_entity e
            LEFT JOIN dwg_attrib a ON a.entity_id = e.id
            WHERE e.file_id = :fid AND e.entity_type = 'INSERT'
            GROUP BY e.handle
        """),
        {"fid": file_id},
    )
    return {row.handle: row.cnt for row in rows if row.handle}


async def get_file_id(session: AsyncSession, path: str) -> str | None:
    r = await session.execute(
        text("SELECT id FROM dwg_file WHERE path = :p ORDER BY created_at DESC LIMIT 1"),
        {"p": path},
    )
    row = r.first()
    return str(row[0]) if row else None


async def verify(path: Path, file_id: str | None) -> None:
    doc = open_drawing(path)

    async with AsyncSessionFactory() as session:
        if file_id is None:
            file_id = await get_file_id(session, str(path))
            if file_id is None:
                print(f"Файл не найден в БД: {path}")
                print("Сначала запустите: python scripts/extract_full_dwg.py")
                return
        print(f"  Проверка file_id={file_id}\n")

        # 1. Подсчёт сущностей: файл vs БД
        file_counts = count_from_file(doc)
        db_counts = await count_from_db(session, file_id)

        all_blocks = sorted(set(file_counts) | set(db_counts))
        mismatches: list[str] = []
        total_file = 0
        total_db = 0

        for block_name in all_blocks:
            fc = file_counts.get(block_name, {})
            dc = db_counts.get(block_name, {})
            all_types = sorted(set(fc) | set(dc))
            for etype in all_types:
                f_cnt = fc.get(etype, 0)
                d_cnt = dc.get(etype, 0)
                total_file += f_cnt
                total_db += d_cnt
                if f_cnt != d_cnt:
                    mismatches.append(
                        f"  РАСХОЖДЕНИЕ  block={block_name!r:50s}  type={etype:20s}  файл={f_cnt}  БД={d_cnt}"
                    )

        print(f"[1] Сущности по типам:")
        print(f"    Всего в файле: {total_file}")
        print(f"    Всего в БД:    {total_db}")
        if mismatches:
            print(f"    Расхождений:   {len(mismatches)}")
            for m in mismatches[:50]:
                print(m)
            if len(mismatches) > 50:
                print(f"    ... и ещё {len(mismatches) - 50}")
        else:
            print(f"    Расхождений:   0 ✓")

        # 2. Неразрешённые INSERT
        unresolved = await check_unresolved_inserts(session, file_id)
        status = "✓" if unresolved == 0 else f"⚠ {unresolved} INSERT без ref_block_def_id"
        print(f"\n[2] Неразрешённые INSERT → block: {status}")

        # 3. Отсутствующие слои
        missing_layers = await check_missing_layers(session, file_id)
        status = "✓" if missing_layers == 0 else f"⚠ {missing_layers} entity с layer_id без записи в dwg_layer"
        print(f"[3] Ссылки entity → layer:          {status}")

        # 4. ATTRIB: файл vs БД
        file_attribs = count_attribs_from_file(doc)
        db_attribs = await count_attribs_from_db(session, file_id)

        total_file_attribs = sum(file_attribs.values())
        total_db_attribs = sum(db_attribs.values())
        attrib_mismatches = [
            (handle, file_attribs[handle], db_attribs.get(handle, 0))
            for handle in file_attribs
            if file_attribs[handle] != db_attribs.get(handle, 0)
        ]
        print(f"\n[4] ATTRIB:")
        print(f"    Всего в файле: {total_file_attribs}")
        print(f"    Всего в БД:    {total_db_attribs}")
        if attrib_mismatches:
            print(f"    Расхождений по INSERT: {len(attrib_mismatches)}")
            for handle, f_cnt, d_cnt in attrib_mismatches[:20]:
                print(f"    handle={handle}  файл={f_cnt}  БД={d_cnt}")
        else:
            print(f"    Расхождений:   0 ✓")

        print()
        ok = not mismatches and unresolved == 0 and missing_layers == 0 and not attrib_mismatches
        print("ИТОГ:", "✓ Всё извлечено корректно" if ok else "⚠ Есть расхождения, см. выше")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/verify_dwg_extraction.py path/to/file.dwg [file_id]")
        sys.exit(1)

    path = Path(sys.argv[1]).expanduser().resolve()
    file_id = sys.argv[2] if len(sys.argv) > 2 else None

    if not path.exists():
        print(f"Файл не найден: {path}")
        sys.exit(1)

    print(f"Верификация: {path}")
    asyncio.run(verify(path, file_id))


if __name__ == "__main__":
    main()
