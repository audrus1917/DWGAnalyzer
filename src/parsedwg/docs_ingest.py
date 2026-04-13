from __future__ import annotations

import asyncio
from pathlib import Path

from openpyxl import load_workbook
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from .db import async_session_factory
from .orm import Entity, EntityType

SUPPORTED_DOC_SUFFIXES = {".pdf", ".docx", ".xlsx"}


def _discover_documents(source_path: Path) -> list[Path]:
    if not source_path.exists():
        raise FileNotFoundError(f"Путь {source_path} не найден.")

    if source_path.is_file():
        if source_path.suffix.lower() not in SUPPORTED_DOC_SUFFIXES:
            raise ValueError("Поддерживаются только PDF, DOCX и XLSX файлы.")
        return [source_path]

    files = sorted(
        item
        for item in source_path.rglob("*")
        if item.is_file() and item.suffix.lower() in SUPPORTED_DOC_SUFFIXES
    )
    if not files:
        raise ValueError(f"В каталоге {source_path} не найдено PDF/DOCX/XLSX файлов.")
    return files


def _extract_docx_text(path: Path) -> str:
    from docx import Document

    document = Document(str(path))
    chunks: list[str] = []

    chunks.extend(
        paragraph.text.strip()
        for paragraph in document.paragraphs
        if paragraph.text and paragraph.text.strip()
    )

    for table in document.tables:
        for row in table.rows:
            values = [cell.text.strip() for cell in row.cells if cell.text and cell.text.strip()]
            if values:
                chunks.append(" | ".join(values))

    return "\n".join(chunks)


def _extract_xlsx_text(path: Path) -> str:
    workbook = load_workbook(filename=str(path), data_only=True, read_only=True)
    chunks: list[str] = []
    try:
        for sheet in workbook.worksheets:
            chunks.append(f"# {sheet.title}")
            for row in sheet.iter_rows(values_only=True):
                values = [str(value).strip() for value in row if value not in (None, "")]
                if values:
                    chunks.append(" | ".join(values))
    finally:
        workbook.close()
    return "\n".join(chunks)


def _extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    chunks: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        normalized = text.strip()
        if normalized:
            chunks.append(normalized)
    return "\n\n".join(chunks)


def _extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _extract_docx_text(path)
    if suffix == ".xlsx":
        return _extract_xlsx_text(path)
    if suffix == ".pdf":
        return _extract_pdf_text(path)
    raise ValueError(f"Неподдерживаемый тип документа: {path.suffix}")


async def _save_documents_to_db(source_path: Path, documents: list[Path]) -> int:
    created = 0

    async with async_session_factory() as session:
        session: AsyncSession

        root = Entity(
            name=source_path.name if source_path.name else str(source_path),
            description="Корневая папка импортированных документов PDF/DOCX/XLSX",
            entity_type=EntityType.folder,
            data={"path": str(source_path)},
            start_from=str(source_path),
        )
        session.add(root)
        await session.flush()

        for doc_path in documents:
            text = _extract_text(doc_path)
            try:
                rel_path = str(doc_path.relative_to(source_path))
            except ValueError:
                rel_path = doc_path.name

            entity = Entity(
                name=doc_path.name,
                description=text,
                entity_type=EntityType.file,
                data={
                    "doc_type": doc_path.suffix.lower().lstrip("."),
                    "relative_path": rel_path,
                    "size_bytes": doc_path.stat().st_size,
                },
                start_from=str(doc_path),
                parent_id=root.id,
            )
            session.add(entity)
            created += 1

        await session.commit()

    return created


def run_documents_ingest(source_path: Path) -> dict[str, object]:
    """Рекурсивно импортирует PDF/DOCX/XLSX документы в таблицу entity."""

    source = source_path.resolve()
    documents = _discover_documents(source)
    created = asyncio.run(_save_documents_to_db(source, documents))
    return {
        "doc_count": len(documents),
        "created_entities": created,
        "source": str(source),
    }


__all__ = ["run_documents_ingest", "SUPPORTED_DOC_SUFFIXES"]
