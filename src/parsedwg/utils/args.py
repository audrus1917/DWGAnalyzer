"""Utilities for building the command-line argument parser."""

import argparse
import logging

from gettext import gettext as _

from src.parsedwg.settings import settings


logger = logging.getLogger(__name__)


def build_args_parser() -> argparse.ArgumentParser:
    """Return the command-line argument parser."""

    readfile_common = argparse.ArgumentParser(add_help=False)
    readfile_common.add_argument("file_path", help="Path to a DWG or DXF file")

    output_common = argparse.ArgumentParser(add_help=False)
    output_common.add_argument("-o", "--output", default=None, help="Output file")

    parser = argparse.ArgumentParser(
        prog="parsedwg",
        description=_("Work with DWG/DXF files: inspect data and run operations"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_block_parser = subparsers.add_parser(
        "extract-block",
        parents=[readfile_common],
        help=_("Extract a block into a separate file."),
    )
    extract_block_parser.add_argument("block_name", help=_("Block name to extract"))

    describe_block_parser = subparsers.add_parser(
        "describe-block",
        parents=[readfile_common, output_common],
        help=_("Read a file and print a block description by name."),
    )
    describe_block_parser.add_argument("block_name", help=_("Block name to describe"))

    export_block_parser = subparsers.add_parser(
        "export-block",
        parents=[readfile_common, output_common],
        help=_("Export the selected block to PNG."),
    )
    export_block_parser.add_argument("block_name", help=_("Block name to export"))
    export_block_parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help=_("PNG resolution for export (default: 300)."),
    )

    export_block_png_parser = subparsers.add_parser(
        "export-block-png",
        parents=[readfile_common, output_common],
        help=_("Export the selected block to PNG."),
    )
    export_block_png_parser.add_argument("block_name", help=_("Block name to export"))
    export_block_png_parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="PNG resolution for export (default: 300).",
    )

    parse_command_parser = subparsers.add_parser(
        "parse",
        help=(
            "Walk a directory recursively, find DWG/DXF files (including ZIP)"
            " and load the block/layer tree into the database."
        ),
    )
    parse_command_parser.add_argument(
        "path",
        help="Path to a directory or file.",
    )
    parse_command_parser.add_argument(
        "--project",
        "-p",
        type=str,
        dest="project",
        default=None,
        help="Name of an existing project.",
    )
    parse_command_parser.add_argument(
        "--dry",
        action="store_true",
        help="Parse the source and print a summary without saving results to the database.",
    )
    parse_command_parser.add_argument(
        "--detail-level",
        choices=["low", "medium", "high"],
        default="high",
        help=(
            "Detail level for saved block and primitive data "
            "(default: high)."
        ),
    )

    agent_run_parser = subparsers.add_parser(
        "agent-run",
        help="Run the agent pipeline for a file or directory.",
    )
    agent_run_parser.add_argument(
        "input_ref",
        help="Path to a file or directory for the agent run.",
    )
    agent_run_parser.add_argument(
        "--profile",
        choices=["full", "interpret-only"],
        default="full",
        help="Agent run profile (default: full).",
    )
    agent_run_parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel AI tasks (default: 1).",
    )
    agent_run_parser.add_argument(
        "--dry",
        action="store_true",
        help="Build and execute the plan without saving AI results to the database.",
    )
    agent_run_parser.add_argument(
        "--project",
        dest="project_name",
        default=None,
        help="Project name used to attach agent-run results.",
    )

    agent_status_parser = subparsers.add_parser(
        "agent-status",
        help="Show the status of an agent job and its steps.",
    )
    agent_status_parser.add_argument("job_id", type=int, help="Agent job ID.")

    interpret_parser = subparsers.add_parser(
        "interpret",
        help=_(
            "Request LLM name interpretations for all entities of a type and "
            "save them to entity_embedding.short_interpretation."
        ),
    )
    interpret_parser.add_argument(
        "--entity-id",
        dest="entity_ids",
        action="append",
        default=None,
        help=_("Entity ID. Can be provided multiple times."),
    )
    interpret_parser.add_argument(
        "--entity-type",
        dest="entity_type",
        default=None,
        help=_("Entity type from the entity_type field, for example BLOCK."),
    )
    interpret_parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help=_("Number of parallel AI requests (default: 1)."),
    )
    interpret_parser.add_argument(
        "--dry",
        action="store_true",
        help=_("Do not save to the database, print a JSON preview instead."),
    )

    verify_parser = subparsers.add_parser(
        "verify",
        parents=[readfile_common],
        help=_("Compare a DWG/DXF file with entities stored in the current database."),
    )
    verify_parser.add_argument(
        "--file-id",
        dest="file_id",
        default=None,
        help=_("ID of the file entity in the database."),
    )

    project_add_parser = subparsers.add_parser(
        "project-add",
        help="Add a project.",
    )
    project_add_parser.add_argument("name", help="Project name.")
    project_add_parser.add_argument(
        "--description",
        dest="description",
        default=None,
        help="Project description.",
    )
    project_add_parser.add_argument(
        "--created-by",
        dest="created_by",
        default=None,
        help="Who created the project.",
    )

    project_update_parser = subparsers.add_parser(
        "project-update",
        help="Update an existing project.",
    )
    project_update_parser.add_argument("project_id", help="Project UUID.")
    project_update_parser.add_argument("--name", dest="name", default=None, help="New name.")
    project_update_parser.add_argument(
        "--description",
        dest="description",
        default=None,
        help="New description.",
    )
    project_update_parser.add_argument(
        "--created-by",
        dest="created_by",
        default=None,
        help="New created_by value.",
    )

    project_delete_parser = subparsers.add_parser(
        "project-delete",
        help="Delete a project.",
    )
    project_delete_parser.add_argument("project_id", help="Project UUID.")
    project_delete_parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm deletion without an interactive prompt.",
    )

    category_add_parser = subparsers.add_parser(
        "category-add",
        help="Add a category.",
    )
    category_add_parser.add_argument("name", help="Category name.")
    category_add_parser.add_argument(
        "--description",
        dest="description",
        default=None,
        help="Category description.",
    )
    category_add_parser.add_argument(
        "--parent-id",
        dest="parent_id",
        default=None,
        help="Parent category UUID.",
    )

    category_update_parser = subparsers.add_parser(
        "category-update",
        help="Update an existing category.",
    )
    category_update_parser.add_argument("category_id", help="Category UUID.")
    category_update_parser.add_argument("--name", dest="name", default=None, help="New name.")
    category_update_parser.add_argument(
        "--description",
        dest="description",
        default=None,
        help="New description.",
    )
    category_update_parser.add_argument(
        "--parent-id",
        dest="parent_id",
        default=None,
        help="New parent category UUID.",
    )

    category_delete_parser = subparsers.add_parser(
        "category-delete",
        help="Delete a category.",
    )
    category_delete_parser.add_argument("category_id", help="Category UUID.")
    category_delete_parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm deletion without an interactive prompt.",
    )

    category_list_parser = subparsers.add_parser(
        "category-list",
        help="Show the category list.",
    )
    category_list_parser.add_argument(
        "--parent-id",
        dest="parent_id",
        default=None,
        help="Return only direct children of the specified category.",
    )

    ingest_docs_parser = subparsers.add_parser(
        "ingest-docs",
        help="Recursively find PDF/DOCX/XLSX/CSV files and load them into the database for RAG.",
    )
    ingest_docs_parser.add_argument(
        "path",
        help="Path to a file or directory for recursive traversal.",
    )

    subparsers.add_parser(
        "export-interpreted-blocks-xlsx",
        parents=[output_common],
        help="Export all blocks with non-empty short_interpretation to XLSX.",
    )

    return parser

