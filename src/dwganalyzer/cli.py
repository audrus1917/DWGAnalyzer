"""Command-line entry point for DWGAnalyzer."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from contextlib import nullcontext

from . import __version__
from .errors import DWGAnalyzerError
from .i18n import _, using_language
from .reporting import render_json, render_text
from .services import analyze_path


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
    subparsers = parser.add_subparsers(dest="command")
    analyze_parser = subparsers.add_parser(
        "analyze",
        help=_("Analyze drawings and display a report."),
        description=_("Analyze drawings and display a report."),
        add_help=False,
    )
    analyze_parser.add_argument(
        "-h",
        "--help",
        action="help",
        help=_("Show this help message and exit."),
    )
    analyze_parser.add_argument(
        "input",
        help=_("DWG/DXF file, ZIP archive, or directory to analyze."),
    )
    analyze_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        dest="output_format",
        help=_("Report format: text or json (default: text)."),
    )
    analyze_parser.add_argument(
        "--language",
        metavar="LOCALE",
        help=_("Report language, for example en or ru."),
    )
    return parser


def _requested_language(arguments: Sequence[str]) -> str | None:
    for index, argument in enumerate(arguments):
        if argument.startswith("--language="):
            return argument.partition("=")[2] or None
        if argument == "--language" and index + 1 < len(arguments):
            return arguments[index + 1]
    return None


def _run_analysis(input_path: str, output_format: str) -> int:
    try:
        batch = analyze_path(input_path)
    except DWGAnalyzerError as error:
        print(_("Error: {message}").format(message=error), file=sys.stderr)
        return 1

    renderer = render_json if output_format == "json" else render_text
    print(renderer(batch))
    return 1 if batch.failures else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the DWGAnalyzer command-line interface.

    Args:
        argv: Command-line arguments without the executable name. Uses
            ``sys.argv`` when omitted.

    Returns:
        Process exit code.
    """

    arguments = list(sys.argv[1:] if argv is None else argv)
    language = _requested_language(arguments)
    language_context = using_language(language) if language else nullcontext()
    with language_context:
        parser = _build_parser()
        if not arguments:
            parser.print_help()
            return 0

        options = parser.parse_args(arguments)
        if options.command == "analyze":
            return _run_analysis(options.input, options.output_format)

        parser.print_help()
        return 0


__all__ = ["main"]
