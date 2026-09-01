"""Coordinate discovery, loading, parsing, and analysis."""

from __future__ import annotations

from pathlib import Path

from ..errors import (
    AnalysisError,
    ArchiveError,
    ConversionError,
    DrawingReadError,
    DWGAnalyzerError,
    InputError,
)
from ..io import discover_sources, load_drawing
from ..models import AnalysisBatch, ProcessingFailure
from ..parsers import parse_drawing
from .analysis import analyze_drawing

_ERROR_CODES: dict[type[DWGAnalyzerError], str] = {
    InputError: "input_error",
    DrawingReadError: "drawing_read_error",
    ConversionError: "conversion_error",
    ArchiveError: "archive_error",
    AnalysisError: "analysis_error",
}


def _error_code(error: DWGAnalyzerError) -> str:
    return _ERROR_CODES.get(type(error), "processing_error")


def analyze_path(input_path: str | Path) -> AnalysisBatch:
    """Discover and analyze every drawing below an input path.

    Expected failures for individual drawings are collected so that remaining
    sources can still be processed. Input discovery errors are raised to the
    caller because no batch can be created.

    Args:
        input_path: Drawing file, directory, or ZIP archive.

    Returns:
        Successful analyses and per-source failures in discovery order.

    Raises:
        DWGAnalyzerError: If the input itself cannot be inspected.
    """

    path = Path(input_path)
    sources = discover_sources(path)
    analyses = []
    failures = []
    for source in sources:
        try:
            drawing = load_drawing(source)
            summary = parse_drawing(drawing, source=source.reference)
            analyses.append(analyze_drawing(summary))
        except DWGAnalyzerError as error:
            failures.append(
                ProcessingFailure(
                    source=source.reference,
                    code=_error_code(error),
                    message=str(error),
                )
            )

    return AnalysisBatch(
        input_path=str(path),
        analyses=tuple(analyses),
        failures=tuple(failures),
    )
