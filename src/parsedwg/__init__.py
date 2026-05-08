"""Пакет parsedwg."""

from .explorer import DXFExplorer
from .models import ParsedItem
from .table_analysis import AxisCluster, TableAnalysis, TextClusterAnalyzer

__all__ = [
    "AxisCluster",
    "DXFExplorer",
    "ParsedItem",
    "TableAnalysis",
    "TextClusterAnalyzer",
]

__version__ = "0.1.0"
