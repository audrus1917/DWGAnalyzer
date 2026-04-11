"""Helpers for detecting table-like text layouts in DXF blocks."""

from __future__ import annotations

from dataclasses import dataclass


type TextEntity = tuple[float, float, str]


@dataclass(slots=True)
class AxisCluster:
    """A cluster of close coordinates on one axis."""

    center: float
    count: int


@dataclass(slots=True)
class TableAnalysis:
    """Result of analyzing a block for table-like text structure."""

    total_texts: int
    table_like_texts: int
    x_clusters: list[AxisCluster]
    y_clusters: list[AxisCluster]
    rows: list[list[str]]
    centered_rows: list[int]
    title: str
    is_table: bool


class TextClusterAnalyzer:
    """Анализирует текстовые сущности блока и ищет табличную структуру."""

    @staticmethod
    def _get_text_content(entity) -> str:
        entity_type = entity.dxftype()
        if entity_type == "TEXT" and entity.dxf.hasattr("text"):
            return entity.dxf.text.strip()

        if entity_type == "MTEXT":
            plain_text = getattr(entity, "plain_text", None)
            if callable(plain_text):
                return str(plain_text()).strip()

        return ""

    @staticmethod
    def _cluster_values(values: list[float], tolerance: float) -> list[AxisCluster]:
        if not values:
            return []

        sorted_values = sorted(values)
        clusters: list[list[float]] = [[sorted_values[0]]]
        for value in sorted_values[1:]:
            current_cluster = clusters[-1]
            center = sum(current_cluster) / len(current_cluster)
            if abs(value - center) <= tolerance:
                current_cluster.append(value)
            else:
                clusters.append([value])

        return [
            AxisCluster(center=sum(cluster) / len(cluster), count=len(cluster))
            for cluster in clusters
            if len(cluster) > 1
        ]

    @staticmethod
    def _find_cluster_index(
        value: float,
        clusters: list[AxisCluster],
        tolerance: float,
    ) -> int | None:
        best_index: int | None = None
        best_distance: float | None = None
        for index, cluster in enumerate(clusters):
            distance = abs(value - cluster.center)
            if distance <= tolerance and (best_distance is None or distance < best_distance):
                best_index = index
                best_distance = distance
        return best_index

    @classmethod
    def _collect_text_entities(cls, block) -> list[TextEntity]:
        text_entities: list[TextEntity] = []
        for entity in block:
            entity_type = entity.dxftype()
            if entity_type not in {"TEXT", "MTEXT"} or not entity.dxf.hasattr("insert"):
                continue

            insert = entity.dxf.insert
            x = getattr(insert, "x", None)
            y = getattr(insert, "y", None)
            if x is None or y is None:
                continue

            text_entities.append((float(x), float(y), cls._get_text_content(entity)))

        return text_entities

    @staticmethod
    def _group_text_rows(
        text_entities: list[TextEntity],
        y_tolerance: float,
    ) -> list[list[TextEntity]]:
        row_centers: list[float] = []
        row_groups: list[list[TextEntity]] = []

        for entity in sorted(text_entities, key=lambda item: (-item[1], item[0])):
            _, y_value, _ = entity
            matched_index: int | None = None
            for index, center in enumerate(row_centers):
                if abs(y_value - center) <= y_tolerance:
                    matched_index = index
                    break

            if matched_index is None:
                row_centers.append(y_value)
                row_groups.append([entity])
                continue

            row = row_groups[matched_index]
            row.append(entity)
            row_centers[matched_index] = sum(item[1] for item in row) / len(row)

        ordered_rows = sorted(
            zip(row_centers, row_groups, strict=False),
            key=lambda item: item[0],
            reverse=True,
        )
        return [sorted(row, key=lambda item: item[0]) for _, row in ordered_rows]

    @staticmethod
    def _build_column_ranges(
        row_groups: list[list[TextEntity]],
        x_tolerance: float,
    ) -> tuple[list[AxisCluster], list[tuple[float, float]]]:
        if not row_groups:
            return [], []

        max_columns = max(len(row) for row in row_groups)
        if max_columns == 0:
            return [], []

        reference_rows = [row for row in row_groups if len(row) == max_columns] or row_groups
        raw_clusters: list[AxisCluster] = []
        for column_index in range(max_columns):
            positions = [row[column_index][0] for row in reference_rows if len(row) > column_index]
            if not positions:
                continue
            raw_clusters.append(
                AxisCluster(
                    center=sum(positions) / len(positions),
                    count=len(positions),
                )
            )

        x_clusters: list[AxisCluster] = []
        for cluster in raw_clusters:
            previous = x_clusters[-1] if x_clusters else None
            if previous is None or abs(cluster.center - previous.center) > x_tolerance:
                x_clusters.append(cluster)
                continue

            merged_count = previous.count + cluster.count
            merged_center = (
                (previous.center * previous.count) + (cluster.center * cluster.count)
            ) / merged_count
            x_clusters[-1] = AxisCluster(center=merged_center, count=merged_count)

        centers = [cluster.center for cluster in x_clusters]
        ranges: list[tuple[float, float]] = []
        for index, center in enumerate(centers):
            left = (centers[index - 1] + center) / 2 if index > 0 else float("-inf")
            right = (
                (center + centers[index + 1]) / 2
                if index < len(centers) - 1
                else float("inf")
            )
            ranges.append((left, right))

        return x_clusters, ranges

    @staticmethod
    def _build_y_clusters(row_groups: list[list[TextEntity]]) -> list[AxisCluster]:
        return [
            AxisCluster(center=max(item[1] for item in row), count=len(row))
            for row in row_groups
            if len(row) > 1
        ]

    @staticmethod
    def _find_range_index(value: float, ranges: list[tuple[float, float]]) -> int | None:
        for index, (left, right) in enumerate(ranges):
            if left <= value < right:
                return index
        return None

    @classmethod
    def _assign_columns_for_row(
        cls,
        row: list[TextEntity],
        column_ranges: list[tuple[float, float]],
    ) -> list[int | None]:
        assignments: list[int | None] = []
        column_count = len(column_ranges)
        strict_order = len(row) <= column_count

        for index, (x_value, _, _) in enumerate(row):
            preferred_index = cls._find_range_index(x_value, column_ranges)
            last_index = assignments[-1] if assignments else None
            min_index = (last_index + 1) if strict_order and last_index is not None else 0
            max_index = column_count - (len(row) - index)
            if not strict_order:
                max_index = column_count - 1

            if preferred_index is None:
                column_index = min_index
            else:
                column_index = min(max(preferred_index, min_index), max_index)

            assignments.append(column_index)

        return assignments

    @classmethod
    def _build_table_rows(
        cls,
        row_groups: list[list[TextEntity]],
        column_ranges: list[tuple[float, float]],
    ) -> tuple[list[list[str]], int, list[int]]:
        if not row_groups or not column_ranges:
            return [], 0, []

        rows: list[list[str]] = []
        centered_rows: list[int] = []
        assigned_count = 0

        for row in row_groups:
            if len(row) < len(column_ranges):
                continue

            cells = ["" for _ in column_ranges]
            assignments = cls._assign_columns_for_row(row, column_ranges)
            for (_, _, text_value), column_index in zip(row, assignments, strict=False):
                if column_index is None or not text_value:
                    continue

                existing_value = cells[column_index]
                if existing_value and text_value not in existing_value.splitlines():
                    cells[column_index] = f"{existing_value}\n{text_value}"
                else:
                    cells[column_index] = text_value
                assigned_count += 1

            if any(cell.strip() for cell in cells):
                rows.append(cells)

        return rows, assigned_count, centered_rows

    @classmethod
    def analyze_table(
        cls,
        block,
        x_tolerance: float = 10.0,
        y_tolerance: float = 3.0,
    ) -> TableAnalysis:
        text_entities = cls._collect_text_entities(block)
        row_groups = cls._group_text_rows(text_entities, y_tolerance)
        x_clusters, column_ranges = cls._build_column_ranges(row_groups, x_tolerance)
        y_clusters = cls._build_y_clusters(row_groups)

        rows, assigned_count, centered_rows = cls._build_table_rows(row_groups, column_ranges)
        is_table = len(x_clusters) >= 2 and len(y_clusters) >= 2 and len(rows) >= 2

        title = ""
        if row_groups and len(row_groups[0]) == 1:
            title = row_groups[0][0][2].strip()

        return TableAnalysis(
            total_texts=len(text_entities),
            table_like_texts=assigned_count,
            x_clusters=x_clusters,
            y_clusters=y_clusters,
            rows=rows,
            centered_rows=centered_rows,
            title=title,
            is_table=is_table,
        )


__all__ = ["AxisCluster", "TableAnalysis", "TextClusterAnalyzer", "TextEntity"]
