"""Класс для получения данных о свойствах DWG/DXF файлов и выполнения операций с ними."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable

from pathlib import Path

from ezdxf.document import Drawing
from ezdxf.filemanagement import readfile
from ezdxf.addons.odafc import readfile as read_odafc
from openpyxl import Workbook
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter

from .table_analysis import TableAnalysis, TextClusterAnalyzer

logger = logging.getLogger(__name__)

type ExplorerRow = dict[str, object]


class DXFExplorer:
    """Класс для получения данных и выполнения операций с DWG/DXF файлами."""

    def __init__(self, drawing: Path | str):
        self.drawing = Path(drawing)
        if not self.drawing.is_file():
            logger.error("Файл %s не найден.", self.drawing)
            raise FileNotFoundError(f"Файл {self.drawing} не найден.")

        size_mb = self.drawing.stat().st_size / (1024 * 1024)
        logger.info("Обрабатываемый файл: %s", self.drawing)
        logger.info("Размер файла: %.2f МБ", size_mb)

    def _read_document(self) -> Drawing:
        """Читает DWG/DXF файл и возвращает объект документа ezdxf."""

        logger.debug("Читаем файл через ezdxf: %s", self.drawing)
        if self.drawing.suffix.lower() == ".dwg":
            logger.info(
                "Файл %s имеет формат DWG, сначала конвертируем его в DXF.",
                self.drawing,
            )
            return read_odafc(self.drawing, "ACAD2018")
        else:
            return readfile(self.drawing)

    @staticmethod
    def format_point(point: object | None) -> str:
        """Возвращает строку с представлением координат точки."""
        if point is None:
            return "n/a"

        x = getattr(point, "x", None)
        y = getattr(point, "y", None)
        z = getattr(point, "z", 0.0)
        if x is not None and y is not None:
            return f"({x:.2f}, {y:.2f}, {z:.2f})"

        if isinstance(point, (tuple, list)) and len(point) >= 2:
            try:
                x = float(point[0])
                y = float(point[1])
                z = float(point[2]) if len(point) >= 3 else 0.0
            except (TypeError, ValueError):
                return str(point)
            return f"({x:.2f}, {y:.2f}, {z:.2f})"

        return str(point)

    @staticmethod
    def is_point(value: object) -> bool:
        """Возвращает True, если значение похоже на точку с координатами 
        (имеет x/y или похожую структуру).
        """
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

    @staticmethod
    def get_text_content(entity) -> str:
        """Возвращает содержимое атрибута `text` объекта."""

        entity_type = entity.dxftype()
        if entity_type == "TEXT" and entity.dxf.hasattr("text"):
            return entity.dxf.text.strip()

        if entity_type == "MTEXT":
            plain_text = getattr(entity, "plain_text", None)
            if callable(plain_text):
                return str(plain_text()).strip()

        return ""

    @classmethod
    def _collect_entity_layers(
        cls,
        doc,
        entity,
        seen_blocks: set[str] | None = None,
    ) -> set[str]:
        """Собирает все слои, на которых находится сущность, включая вложенные блоки."""
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

        nested_seen_blocks = {*seen_blocks, block_name}
        for nested_entity in block:
            layers.update(cls._collect_entity_layers(doc, nested_entity, nested_seen_blocks))

        return layers

    @classmethod
    def _get_layout_layers(cls, doc, layout) -> str:
        """Возвращает строку с перечислением всех слоев, на которых находятся сущности в макете."""
        layers: set[str] = set()
        for entity in layout:
            layers.update(cls._collect_entity_layers(doc, entity))
        return ", ".join(sorted(layers)) if layers else "-"

    @classmethod
    def _get_entity_params(cls, entity) -> dict[str, str]:
        """Возвращает словарь с параметрами сущности."""
        entity_type = entity.dxftype()
        params: dict[str, str] = {"type": entity_type}

        if entity_type == "INSERT" and entity.dxf.hasattr("name"):
            params["block"] = entity.dxf.name

        for attr_name, value in entity.dxf.all_existing_dxf_attribs().items():
            if cls.is_point(value):
                params[attr_name] = cls.format_point(value)

        text_value = cls.get_text_content(entity)
        if text_value:
            params["text"] = text_value

        if entity_type == "LWPOLYLINE":
            get_points = getattr(entity, "get_points", None)
            if callable(get_points):
                raw_points = get_points("xy")
                if isinstance(raw_points, (list, tuple)):
                    points = [
                        f"({point[0]:.2f}, {point[1]:.2f}, 0.00)"
                        for point in raw_points
                    ]
                    if points:
                        params["points"] = f"[{', '.join(points)}]"
        elif entity_type == "POLYLINE":
            get_points = getattr(entity, "points", None)
            if callable(get_points):
                raw_points = get_points()
                if isinstance(raw_points, Iterable):
                    points = [cls.format_point(point) for point in raw_points]
                    if points:
                        params["points"] = f"[{', '.join(points)}]"
        elif entity_type == "SOLID":
            solid_points = []
            for attr_name in ("vtx0", "vtx1", "vtx2", "vtx3"):
                if entity.dxf.hasattr(attr_name):
                    solid_points.append(cls.format_point(getattr(entity.dxf, attr_name)))
            if solid_points:
                params["points"] = f"[{', '.join(solid_points)}]"

        return params

    @staticmethod
    def _describe_entity(params: dict[str, str]) -> str:
        rendered: list[str] = []
        for key, value in params.items():
            if key in {"block", "text"}:
                rendered.append(f"{key}={value!r}")
            else:
                rendered.append(f"{key}={value}")
        return ", ".join(rendered)

    @classmethod
    def _analyze_text_table(
        cls,
        block,
        x_tolerance: float = 10.0,
        y_tolerance: float = 30.0,
    ) -> TableAnalysis:
        return TextClusterAnalyzer.analyze_table(
            block,
            x_tolerance=x_tolerance,
            y_tolerance=y_tolerance,
        )

    def _export_table_to_xlsx(
        self,
        block_name: str,
        rows: list[list[str]],
        centered_rows: list[int],
        title: str,
    ) -> Path:
        fallback_name = f"{self.drawing.stem}-{block_name}"
        file_stem = title or fallback_name
        safe_file_name = re.sub(r"[^0-9A-Za-zА-Яа-я._-]+", "_", file_stem).strip("_")
        safe_file_name = safe_file_name or fallback_name
        safe_sheet_name = re.sub(r"[^0-9A-Za-zА-Яа-я._-]+", "_", block_name).strip("_") or "block"
        output_path = self.drawing.with_name(f"{safe_file_name}.xlsx")

        workbook = Workbook()
        sheet = workbook.active
        if sheet is None:
            sheet = workbook.create_sheet()
        sheet.title = safe_sheet_name[:31]
        sheet.freeze_panes = "A2"

        for row in rows:
            sheet.append([value or None for value in row])

        for row in sheet.iter_rows():
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")

        if rows:
            last_column = len(rows[0])
            for row_index in centered_rows:
                excel_row = row_index + 1
                if last_column > 1:
                    sheet.merge_cells(
                        start_row=excel_row,
                        start_column=1,
                        end_row=excel_row,
                        end_column=last_column,
                    )
                sheet.cell(row=excel_row, column=1).alignment = Alignment(
                    horizontal="center",
                    vertical="center",
                    wrap_text=True,
                )

        for column_index, column_cells in enumerate(sheet.iter_cols(), start=1):
            values = [str(cell.value) for cell in column_cells if cell.value]
            max_length = max(
                (len(line) for value in values for line in value.splitlines()),
                default=10,
            )
            sheet.column_dimensions[get_column_letter(column_index)].width = min(max_length + 2, 60)

        workbook.save(output_path)
        return output_path

    def list_layouts(self) -> list[ExplorerRow]:
        """Возвращает список layout'ов для текущего DXF/DWG файла."""

        logger.info("Считываем layout'ы для файла: %s", self.drawing)
        doc = self._read_document()
        return [
            {
                "drawing": str(self.drawing),
                "layout": layout.name,
                "layers": self._get_layout_layers(doc, layout),
            }
            for layout in doc.layouts
        ]

    def list_blocks(self) -> list[ExplorerRow]:
        """Возвращает список блоков для текущего DXF/DWG файла."""

        logger.info("Считываем блоки для файла: %s", self.drawing)
        doc = self._read_document()
        rows: list[ExplorerRow] = []
        for block in doc.blocks:
            logger.debug("Block: %s", block.name)
            rows.append(
                {
                    "drawing": str(self.drawing),
                    "block": block.name,
                    "entity_count": sum(1 for _ in block),
                }
            )
            for entity in block:
                params = self._get_entity_params(entity)
                logger.debug("  Entity: %s", self._describe_entity(params))
        return rows

    def extract_block(self, block_name: str) -> None:
        logger.info("Извлекаем блок '%s' из файла: %s", block_name, self.drawing)
        doc = self._read_document()
        block = doc.blocks.get(block_name)
        if block is None:
            logger.error("Блок '%s' не найден в файле.", block_name)
            raise ValueError(f"Блок '{block_name}' не найден в файле.")

        for entity in block:
            params = self._get_entity_params(entity)
            logger.debug("  Entity: %s", self._describe_entity(params))

        table_stats = self._analyze_text_table(block)
        logger.info(
            "TEXT/MTEXT: всего=%s, близко по X/Y=%s, X-групп=%s, Y-групп=%s",
            table_stats.total_texts,
            table_stats.table_like_texts,
            len(table_stats.x_clusters),
            len(table_stats.y_clusters),
        )

        if table_stats.is_table:
            output_path = self._export_table_to_xlsx(
                block_name,
                table_stats.rows,
                table_stats.centered_rows,
                table_stats.title,
            )
            logger.info("Таблица сохранена в XLSX: %s", output_path)
        else:
            logger.info("Табличная структура не определена, XLSX не создан.")


__all__ = ["DXFExplorer"]
