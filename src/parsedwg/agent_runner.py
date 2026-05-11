"""Оркестратор агентного пайплайна."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .agent_db import (
    create_agent_job,
    create_agent_job_steps,
    get_agent_job,
    list_agent_job_steps,
    mark_job_completed,
    mark_job_failed,
    mark_job_running,
    mark_step_completed,
    mark_step_failed,
    mark_step_running,
    mark_step_skipped,
)
from .agent_types import AgentJobStatus, AgentProfile, AgentStepKind
from .agent_workers import (
    run_categorize_entities_step,
    run_interpret_blocks_step,
    run_verify_extraction_step,
)


class AgentRunner:
    def __init__(
        self,
        ai_model: str,
        ai_base_url: str,
        ai_api_key: str,
        workers: int,
        dry: bool,
        project_name: str | None = None,
    ) -> None:
        self.ai_model = ai_model
        self.ai_base_url = ai_base_url
        self.ai_api_key = ai_api_key
        self.workers = workers
        self.dry = dry
        self.project_name = project_name

    async def build_plan(self, input_ref: str, profile: str) -> list[dict[str, object]]:
        steps: list[dict[str, object]] = [
            {
                "step_kind": AgentStepKind.INTERPRET_BLOCKS.value,
                "input_json": {
                    "file_ref": input_ref,
                    "by_path": True,
                    "project_name": self.project_name,
                },
            }
        ]
        steps.append(
            {
                "step_kind": AgentStepKind.CATEGORIZE_ENTITIES.value,
                "input_json": {
                    "file_ref": input_ref,
                    "by_path": True,
                    "entity_type": "BLOCK",
                },
            }
        )
        if profile == AgentProfile.FULL.value and Path(input_ref).is_file():
            steps.append(
                {
                    "step_kind": AgentStepKind.VERIFY_EXTRACTION.value,
                    "input_json": {
                        "drawing_path": input_ref,
                        "file_id": None,
                    },
                }
            )
        return steps

    async def create_job(self, input_ref: str, profile: str) -> int:
        job = await create_agent_job(
            input_ref=input_ref,
            profile=profile,
            file_id=None,
            project_id=None,
            options_json={
                "dry": self.dry,
                "workers": self.workers,
                "project_name": self.project_name,
            },
        )
        await create_agent_job_steps(job["id"], await self.build_plan(input_ref=input_ref, profile=profile))
        return int(job["id"])

    async def run_job(self, job_id: int) -> dict[str, object]:
        job = await get_agent_job(job_id)
        if job is None:
            raise LookupError(f"Agent job {job_id} not found.")

        await mark_job_running(job_id)
        steps = await list_agent_job_steps(job_id)
        try:
            for step in steps:
                await mark_step_running(int(step["id"]))
                try:
                    result = await self.run_step(str(step["step_kind"]), step.get("input_json") or {})
                except Exception as exc:
                    await mark_step_failed(int(step["id"]), str(exc))
                    raise
                if result.get("status") == "skipped":
                    await mark_step_skipped(int(step["id"]), result)
                else:
                    await mark_step_completed(int(step["id"]), result)

            await mark_job_completed(job_id, AgentJobStatus.COMPLETED.value)
        except Exception as exc:
            await mark_job_failed(job_id, str(exc))
            raise

        updated_steps = await list_agent_job_steps(job_id)
        return self.build_summary(job_id, updated_steps)

    async def run_step(self, step_kind: str, input_json: dict[str, object]) -> dict[str, object]:
        if step_kind == AgentStepKind.INTERPRET_BLOCKS.value:
            return await run_interpret_blocks_step(
                file_ref=str(input_json["file_ref"]),
                by_path=bool(input_json.get("by_path", False)),
                project_name=(
                    str(input_json["project_name"])
                    if input_json.get("project_name") is not None
                    else None
                ),
                ai_model=self.ai_model,
                ai_base_url=self.ai_base_url,
                ai_api_key=self.ai_api_key,
                workers=self.workers,
                dry=self.dry,
            )

        if step_kind == AgentStepKind.VERIFY_EXTRACTION.value:
            drawing_path = Path(str(input_json["drawing_path"]))
            if not drawing_path.is_file():
                return {
                    "status": "skipped",
                    "reason": "verify_extraction поддерживается только для одного файла.",
                }
            return await run_verify_extraction_step(
                drawing_path=drawing_path,
                file_id=str(input_json["file_id"]) if input_json.get("file_id") else None,
            )

        if step_kind == AgentStepKind.CATEGORIZE_ENTITIES.value:
            return await run_categorize_entities_step(
                file_ref=str(input_json["file_ref"]),
                by_path=bool(input_json.get("by_path", False)),
                entity_type=str(input_json["entity_type"]),
                ai_model=self.ai_model,
                ai_base_url=self.ai_base_url,
                ai_api_key=self.ai_api_key,
                workers=self.workers,
                dry=self.dry,
            )

        raise ValueError(f"Unsupported step kind: {step_kind}")

    def build_summary(self, job_id: int, steps: list[dict[str, Any]]) -> dict[str, object]:
        return {
            "job_id": job_id,
            "steps_total": len(steps),
            "steps_completed": sum(1 for step in steps if step["status"] == "completed"),
            "steps_failed": sum(1 for step in steps if step["status"] == "failed"),
            "steps_skipped": sum(1 for step in steps if step["status"] == "skipped"),
        }