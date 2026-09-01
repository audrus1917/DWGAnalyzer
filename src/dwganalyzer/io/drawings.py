"""Load DWG and DXF drawings behind a single input boundary."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import ezdxf
from ezdxf.addons import odafc
from ezdxf.document import Drawing

from ..errors import ConversionError, DrawingReadError, InputError
from ..i18n import _
from ..models import DrawingSource
from .archives import extract_drawing


def _load_dxf(path: Path) -> Drawing:
    try:
        return ezdxf.readfile(path)
    except ezdxf.DXFStructureError as exc:
        raise DrawingReadError(
            _("Invalid or corrupted DXF drawing: {path}").format(path=path)
        ) from exc
    except UnicodeDecodeError as exc:
        raise DrawingReadError(
            _("Unable to decode DXF drawing: {path}").format(path=path)
        ) from exc
    except OSError as exc:
        raise DrawingReadError(
            _("Unable to read DXF drawing: {path}").format(path=path)
        ) from exc


def _load_dwg(path: Path) -> Drawing:
    if not odafc.is_installed():
        raise ConversionError(
            _("ODA File Converter is required to read DWG drawings.")
        )

    try:
        return odafc.readfile(path)
    except odafc.ODAFCNotInstalledError as exc:
        raise ConversionError(
            _("ODA File Converter is required to read DWG drawings.")
        ) from exc
    except (
        odafc.UnknownODAFCError,
        odafc.UnsupportedFileFormat,
        odafc.UnsupportedVersion,
        OSError,
    ) as exc:
        raise ConversionError(
            _("Unable to convert DWG drawing: {path}").format(path=path)
        ) from exc


def _load_path(path: Path) -> Drawing:
    if not path.is_file():
        raise InputError(_("Drawing file does not exist: {path}").format(path=path))

    suffix = path.suffix.lower()
    if suffix == ".dxf":
        return _load_dxf(path)
    if suffix == ".dwg":
        return _load_dwg(path)
    raise InputError(_("Unsupported drawing format: {path}").format(path=path))


def load_drawing(source: DrawingSource | str | Path) -> Drawing:
    """Load a drawing from a file or validated ZIP member.

    Args:
        source: Drawing source or direct filesystem path.

    Returns:
        Loaded ``ezdxf`` drawing.

    Raises:
        InputError: If the input path or format is unsupported.
        ArchiveError: If an archived drawing cannot be extracted safely.
        DrawingReadError: If a DXF file cannot be read.
        ConversionError: If a DWG file cannot be converted through ODA.
    """

    drawing_source = (
        source if isinstance(source, DrawingSource) else DrawingSource(path=Path(source))
    )
    if drawing_source.archive_member is None:
        return _load_path(drawing_source.path)

    with TemporaryDirectory(prefix="dwganalyzer-") as temp_dir:
        extracted_path = extract_drawing(drawing_source, Path(temp_dir))
        return _load_path(extracted_path)


__all__ = ["load_drawing"]
