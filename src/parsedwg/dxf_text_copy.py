from __future__ import annotations

from pathlib import Path

from ezdxf.addons.importer import Importer
from ezdxf.filemanagement import new, readfile


TEXT_ENTITY_TYPES = {"TEXT", "MTEXT"}


def _text_entities(layout) -> list:
    return [entity for entity in layout if entity.dxftype() in TEXT_ENTITY_TYPES]


def copy_text_entities(
    source_path: str | Path,
    target_path: str | Path,
    *,
    modelspace_only: bool = False,
) -> int:
    source_doc = readfile(Path(source_path))
    target_doc = new(dxfversion=source_doc.dxfversion)
    importer = Importer(source_doc, target_doc)

    copied_count = 0

    source_msp = source_doc.modelspace()
    target_msp = target_doc.modelspace()
    model_entities = _text_entities(source_msp)
    if model_entities:
        importer.import_entities(model_entities, target_msp)
        copied_count += len(model_entities)

    if not modelspace_only:
        for layout in source_doc.layouts:
            if layout.name == "Model":
                continue

            if layout.name in target_doc.layouts:
                target_layout = target_doc.layout(layout.name)
            else:
                target_layout = target_doc.layouts.new(layout.name)

            layout_entities = _text_entities(layout)
            if layout_entities:
                importer.import_entities(layout_entities, target_layout)
                copied_count += len(layout_entities)

    importer.finalize()
    target_doc.saveas(Path(target_path))
    return copied_count
