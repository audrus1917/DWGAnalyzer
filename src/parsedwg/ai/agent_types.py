"""Types for the agent pipeline."""

from __future__ import annotations

from enum import StrEnum


class AgentJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class AgentStepKind(StrEnum):
    INTERPRET_BLOCKS = "interpret_blocks"
    CATEGORIZE_ENTITIES = "categorize_entities"
    VERIFY_EXTRACTION = "verify_extraction"


class AgentProfile(StrEnum):
    FILE = "file"
    FULL = "full"