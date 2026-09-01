"""Command-line entry point for DWGAnalyzer."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import __version__
from .i18n import _


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dwganalyzer",
        description=_("DWG/DXF drawing analyzer"),
        add_help=False,
    )
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        help=_("Show this help message and exit."),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help=_("Show the program version and exit."),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the DWGAnalyzer command-line interface.

    Args:
        argv: Command-line arguments without the executable name. Uses
            ``sys.argv`` when omitted.

    Returns:
        Process exit code.
    """

    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    if not arguments:
        parser.print_help()
        return 0

    parser.parse_args(arguments)
    return 0


__all__ = ["main"]
