"""Utilities for building the command-line argument parser."""

import argparse
import logging

from gettext import gettext as _


logger = logging.getLogger(__name__)


def build_args_parser() -> argparse.ArgumentParser:
    """Return the command-line argument parser."""

    readfile_common = argparse.ArgumentParser(add_help=False)
    readfile_common.add_argument("file_path", help="Path to a DWG or DXF file")

    output_common = argparse.ArgumentParser(add_help=False)
    output_common.add_argument("-o", "--output", default=None, help="Output file")

    filter_common = argparse.ArgumentParser(add_help=False)
    filter_common.add_argument("--file-id", default=None, help="File ID filter")
    filter_common.add_argument(
        "--project",
        "-p",
        type=str,
        dest="project",
        default=None,
        help="Name of an existing project.",
    )


    parser = argparse.ArgumentParser(
        prog="parsedwg",
        description=_("Work with DWG/DXF files: inspect data and run operations"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_block_parser = subparsers.add_parser(
        "export",
        parents=[readfile_common, output_common],
        help=_("Export the selected block to PNG, SVG, DXF."),
    )
    export_block_parser.add_argument("block_name", help=_("Block name to export"))
    export_block_parser.add_argument(
        "--format",
        "-f",
        choices=["png", "svg", "dxf"],
        default="png",
        help=_("Export format (default: png)."),
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

    interpret_parser = subparsers.add_parser(
        "interpret",
        parents=[filter_common],
        help=_(
            "Request LLM name interpretations for all entities of a type and save them."
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

    subparsers.add_parser(
        "verify",
        parents=[readfile_common, filter_common],
        help=_("Compare a DWG/DXF file with entities stored in the current database."),
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

    subparsers.add_parser(
        "project-list",
        help="Show the project list.",
    )

    file_list_parser = subparsers.add_parser(
        "file-list",
        help="Show file entities, optionally filtered by project.",
    )
    file_list_parser.add_argument(
        "--project",
        "-p",
        dest="project",
        default=None,
        help="Project name filter.",
    )

    entity_list_parser = subparsers.add_parser(
        "entity-list",
        help="Show entities of a selected type with optional project and file filters.",
    )
    entity_list_parser.add_argument(
        "--entity-type",
        dest="entity_type",
        required=True,
        help="Entity type from the entity_type field, for example BLOCK.",
    )
    entity_list_parser.add_argument(
        "--project",
        "-p",
        dest="project",
        default=None,
        help="Project name filter.",
    )
    entity_list_parser.add_argument(
        "--file-id",
        dest="file_id",
        default=None,
        help="File ID filter.",
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

    # subparsers.add_parser(
    #     "export-interpreted-blocks-xlsx",
    #     parents=[output_common],
    #     help="Export all blocks with non-empty short_interpretation to XLSX.",
    # )

    return parser

