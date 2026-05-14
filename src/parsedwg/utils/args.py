"""Utilities for building the command-line argument parser."""

import argparse
import logging

from src.parsedwg.settings import settings


logger = logging.getLogger(__name__)


def build_args_parser() -> argparse.ArgumentParser:
    """Return the command-line argument parser."""

    readfile_common = argparse.ArgumentParser(add_help=False)
    readfile_common.add_argument("file_path", help="Path to a DWG or DXF file")

    output_common = argparse.ArgumentParser(add_help=False)
    output_common.add_argument("-o", "--output", default=None, help="Output file")

    ai_common = argparse.ArgumentParser(add_help=False)
    ai_common.add_argument(
        "--ai-model",
        default=settings.ai_model,
        help="Model name for AI mode (default: llama3.1:8b).",
    )
    ai_common.add_argument(
        "--ai-base-url",
        default=settings.ai_base_url,
        help="OpenAI-compatible base URL for the model (default: Ollama).",
    )
    ai_common.add_argument(
        "--ai-api-key",
        default=settings.ai_api_key,
        help="API key for the AI provider (for Ollama the default is fine).",
    )

    parser = argparse.ArgumentParser(
        prog="parsedwg",
        description="Work with DWG/DXF files: inspect data and run operations",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_block_parser = subparsers.add_parser(
        "extract-block",
        parents=[readfile_common],
        help="Extract a block into a separate file.",
    )
    extract_block_parser.add_argument("block_name", help="Block name to extract")

    describe_block_parser = subparsers.add_parser(
        "describe-block",
        parents=[readfile_common, output_common],
        help="Read a file and print a block description by name.",
    )
    describe_block_parser.add_argument("block_name", help="Block name to describe")

    export_block_parser = subparsers.add_parser(
        "export-block",
        parents=[readfile_common, output_common],
        help="Export the selected block to PNG.",
    )
    export_block_parser.add_argument("block_name", help="Block name to export")
    export_block_parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="PNG resolution for export (default: 300).",
    )

    export_block_png_parser = subparsers.add_parser(
        "export-block-png",
        parents=[readfile_common, output_common],
        help="Export the selected block to PNG.",
    )
    export_block_png_parser.add_argument("block_name", help="Block name to export")
    export_block_png_parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="PNG resolution for export (default: 300).",
    )

    process_parser = subparsers.add_parser(
        "process",
        help=(
            "Walk a directory recursively, find DWG/DXF files (including ZIP)"
            " and load the block/layer tree into the database."
        ),
    )
    process_parser.add_argument(
        "path",
        help="Path to a directory or file.",
    )
    process_parser.add_argument(
        "--project",
        "-p",
        type=str,
        dest="project",
        default=None,
        help="Name of an existing project.",
    )
    process_parser.add_argument(
        "--dry",
        action="store_true",
        help="Parse the source and print a summary without saving results to the database.",
    )
    process_parser.add_argument(
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
        parents=[ai_common],
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

    interpret_entities_parser = subparsers.add_parser(
        "interpret-entities",
        parents=[ai_common],
        help="Request LLM name interpretations for all entities of a type and save them to entity_embedding.short_interpretation.",
    )
    interpret_entities_parser.add_argument(
        "--entity-id",
        dest="entity_ids",
        action="append",
        default=None,
        help="Entity ID. Can be provided multiple times.",
    )
    interpret_entities_parser.add_argument(
        "--entity-type",
        dest="entity_type",
        default=None,
        help="Entity type from the entity_type field, for example BLOCK.",
    )
    interpret_entities_parser.add_argument(
        "--extra-context",
        dest="extra_context",
        default="",
        help="Additional context for the LLM, for example a project section.",
    )
    interpret_entities_parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel AI requests (default: 1).",
    )
    interpret_entities_parser.add_argument(
        "--dry",
        action="store_true",
        help="Do not save to the database, print a JSON preview instead.",
    )

    interpret_blocks_parser = subparsers.add_parser(
        "interpret-blocks",
        parents=[ai_common],
        help=(
            "Interpret block names and save results to "
            "entity_embedding.short_interpretation and entity_embedding.full_interpretation."
        ),
    )
    interpret_blocks_parser.add_argument(
        "--block-id",
        dest="block_ids",
        action="append",
        default=None,
        help="Block ID. Can be provided multiple times.",
    )
    interpret_blocks_parser.add_argument(
        "file_ref",
        nargs="?",
        default=None,
        help="File entity ID or file path (when --by-path is used).",
    )
    interpret_blocks_parser.add_argument(
        "--by-path",
        action="store_true",
        help="Look up the file entity by path instead of ID.",
    )
    interpret_blocks_parser.add_argument(
        "--extra-context",
        dest="extra_context",
        default="",
        help="Additional context for the LLM, for example a project section.",
    )
    interpret_blocks_parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel AI requests (default: 1).",
    )
    interpret_blocks_parser.add_argument(
        "--dry",
        action="store_true",
        help="Do not save to the database, print a JSON preview instead.",
    )

    interpret_block_parser = subparsers.add_parser(
        "interpret-block",
        parents=[ai_common],
        help=(
            "Interpret one block name and save results to "
            "entity_embedding.short_interpretation and entity_embedding.full_interpretation."
        ),
    )
    interpret_block_parser.add_argument(
        "--entity-id",
        dest="entity_id",
        required=True,
        help="Block ID in the database.",
    )
    interpret_block_parser.add_argument(
        "--extra-context",
        dest="extra_context",
        default="",
        help="Additional context for the LLM, for example a project section.",
    )
    interpret_block_parser.add_argument(
        "--dry",
        action="store_true",
        help="Do not save to the database, print a JSON preview instead.",
    )

    verify_extraction_parser = subparsers.add_parser(
        "verify-extraction",
        parents=[readfile_common],
        help="Compare a DWG/DXF file with entities stored in the current database.",
    )
    verify_extraction_parser.add_argument(
        "--file-id",
        dest="file_id",
        default=None,
        help="UUID of the file entity in the database.",
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

