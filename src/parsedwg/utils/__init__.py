"""Helper utilities."""

import sys
import json
import zipfile
import logging
import hashlib

from typing import Any
from pathlib import Path
import multiprocessing as mp

from ezdxf.filemanagement import readfile
from ezdxf.addons.odafc import readfile as read_odafc

from src.parsedwg.constants import ResultRow


logger = logging.getLogger(__name__)


def extract_from_zip(zip_path: Path, member: str, temp_dir: Path) -> Path:
    """Extract a file from a ZIP archive into a temporary directory.

    Args:
        zip_path: Path to the ZIP archive.
        member: File name inside the archive.
        temp_dir: Temporary directory used for extraction.

    Returns:
        Path to the extracted temporary file.
    """

    target_path = temp_dir / Path(member).name
    with zipfile.ZipFile(zip_path) as archive:
        data = archive.read(member)
    target_path.write_bytes(data)
    return target_path


def read_drawing(path: Path):
    """Read a DWG/DXF file via ezdxf or ODAFC and return a Drawing.

    Args:
        path: Path to the drawing file.

    Returns:
        Drawing object loaded from the file.
    """

    suffix = path.suffix.lower()
    if suffix == ".dwg":
        return read_odafc(path, "ACAD2018")
    return readfile(path)



def get_workers_number(requested_workers: int) -> int:
    """Return the optimal number of worker processes for conversion.

    The value depends on machine resources and the requested worker count.
    """

    logical_cpus = max(1, mp.cpu_count())
    max_workers = max(1, logical_cpus - 1)
    auto_workers = max(1, min(max_workers, int(logical_cpus * 0.7)))

    if requested_workers <= 0:
        logger.info(
            "Auto-selected workers: logical_cpus=%s, conversion_workers=%s",
            logical_cpus,
            auto_workers,
        )
        return auto_workers

    if requested_workers > max_workers:
        logger.warning(
            "Requested workers=%s, capped at %s (logical_cpus=%s).",
            requested_workers,
            max_workers,
            logical_cpus,
        )
        return max_workers

    return requested_workers


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_table(rows: list[ResultRow]) -> str:
    """Format result rows as a simple ASCII table."""

    if not rows:
        return "No data."

    columns = list(rows[0].keys())
    prepared_rows = [[str(row.get(column, "")) for column in columns] for row in rows]
    widths = {
        column: max(len(column), *(len(values[index]) for values in prepared_rows))
        for index, column in enumerate(columns)
    }

    header = " | ".join(column.ljust(widths[column]) for column in columns)
    separator = "-+-".join("-" * widths[column] for column in columns)
    body = [
        " | ".join(values[index].ljust(widths[column]) for index, column in enumerate(columns))
        for values in prepared_rows
    ]
    return "\n".join([header, separator, *body])


def print_as_table(rows: list[ResultRow]) -> None:
    """Print result rows as a table."""

    print(as_table(rows))


def _write_progress_line(message: str, previous_width: int = 0) -> int:
    """Update a single progress line in stdout."""

    width = max(previous_width, len(message))
    sys.stdout.write("\r" + message.ljust(width))
    sys.stdout.flush()
    return width


def _finish_progress_line(width: int) -> None:
    """Terminate the progress line with a newline."""

    if width <= 0:
        return
    sys.stdout.write("\n")
    sys.stdout.flush()


def _format_duration_seconds(duration_seconds: float) -> str:
    """Format processing duration in seconds."""

    return f"{duration_seconds:.2f} s"

def _save_rows_to_json(output_path: Path, rows: list[ResultRow]) -> None:
    """Save result rows to a JSON file."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _save_payload_to_json(output_path: Path, payload: object) -> None:
    """Save any JSON-serializable payload to a file."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def file_md5(path: Path) -> str:
    """Return the file MD5 hash used to identify content.

    Args:
        path: File path.

    Returns:
        Hex string with the file MD5 hash.
    """

    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_chat_url(base_url: str) -> str:
    """Build the Ollama /api/chat URL from an OpenAI-compatible base URL."""
    stripped = base_url.rstrip("/")
    if stripped.endswith("/v1"):
        stripped = stripped[:-3]
    return stripped.rstrip("/") + "/api/chat"
