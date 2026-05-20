"""Service layer for the agent pipeline."""

from __future__ import annotations

import asyncio

from src.parsedwg.ai.agent_db import get_agent_job, list_agent_job_steps
from src.parsedwg.ai.agent_runner import AgentRunner


def run_agent_job_sync(
    input_ref: str,
    profile: str,
    workers: int,
    dry: bool,
    project_name: str | None = None,
) -> int:
    runner = AgentRunner(
        workers=workers,
        dry=dry,
        project_name=project_name,
    )

    async def _run() -> int:
        job_id = await runner.create_job(input_ref=input_ref, profile=profile)
        await runner.run_job(job_id)
        return job_id

    return asyncio.run(_run())


def get_agent_job_report(job_id: int) -> dict[str, object] | None:
    async def _load() -> dict[str, object] | None:
        job = await get_agent_job(job_id)
        if job is None:
            return None
        steps = await list_agent_job_steps(job_id)
        return {
            "job": job,
            "steps": steps,
        }

    return asyncio.run(_load())