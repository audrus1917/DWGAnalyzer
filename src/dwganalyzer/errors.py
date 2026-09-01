"""Application-specific exception types."""


class DWGAnalyzerError(Exception):
    """Base class for expected DWGAnalyzer failures."""


class InputError(DWGAnalyzerError):
    """Raised when an input source is invalid or unsupported."""


class DrawingReadError(DWGAnalyzerError):
    """Raised when a drawing cannot be read."""


class ConversionError(DWGAnalyzerError):
    """Raised when a DWG drawing cannot be converted."""


class ArchiveError(DWGAnalyzerError):
    """Raised when an archive cannot be inspected or extracted safely."""


class AnalysisError(DWGAnalyzerError):
    """Raised when drawing analysis cannot be completed."""
