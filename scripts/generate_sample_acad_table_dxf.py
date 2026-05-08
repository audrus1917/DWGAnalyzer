#!/usr/bin/env python

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import ezdxf


DEFAULT_SOURCE = Path("_data/samples/n1/new block.dxf")
DEFAULT_OUTPUT = Path("_data/samples/acad_table_reference_sample.dxf")


def materialize_table_sample(source_path: Path, output_path: Path) -> Path:
    doc = ezdxf.readfile(source_path)
    table_count = len(list(doc.modelspace().query("ACAD_TABLE")))
    if table_count == 0:
        raise ValueError(f"Source file {source_path} does not contain ACAD_TABLE in modelspace.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, output_path)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a stable DXF sample with ACAD_TABLE by copying a known-good source file."
        ),
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"Source DXF with ACAD_TABLE. Default: {DEFAULT_SOURCE}",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output DXF path. Default: {DEFAULT_OUTPUT}",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = materialize_table_sample(args.source, args.output)
    print(output_path)


if __name__ == "__main__":
    main()