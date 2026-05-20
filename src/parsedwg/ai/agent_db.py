"""Database operations for the agent pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from src.parsedwg.agent_orm import AgentJob, AgentJobStep
from src.parsedwg.agent_types import AgentJobStatus, AgentStepStatus
from src.parsedwg.db import async_session_factory
from src.parsedwg.settings import settings


def _get_now() -> datetime:
    return datetime.now(settings.tz)


def _job_to_dict(job: AgentJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "status": job.status,
        "profile": job.profile,
        "input_ref": job.input_ref,
        "file_id": job.file_id,
        "project_id": job.project_id,
        "options_json": job.options_json,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


def _step_to_dict(step: AgentJobStep) -> dict[str, Any]:
    return {
        "id": step.id,
        "job_id": step.job_id,
        "step_kind": step.step_kind,
        "status": step.status,
        "step_order": step.step_order,
        "target_file_id": step.target_file_id,
        "input_json": step.input_json,
        "result_json": step.result_json,
        "error_message": step.error_message,
        "started_at": step.started_at,
        "finished_at": step.finished_at,
    }


async def create_agent_job(
    input_ref: str,
    profile: str,
    file_id: int | None = None,
    project_id: int | None = None,
    options_json: dict[str, object] | None = None,
) -> dict[str, Any]:
    async with async_session_factory() as session:
        job = AgentJob(
            status=AgentJobStatus.PENDING.value,
            profile=profile,
            input_ref=input_ref,
            file_id=file_id,
            project_id=project_id,
            options_json=options_json,
        )
        session.add(job)
        await session.flush()
        payload = _job_to_dict(job)
        await session.commit()
        return payload


async def create_agent_job_steps(
    job_id: int,
    steps: list[dict[str, object]],
) -> list[dict[str, Any]]:
    async with async_session_factory() as session:
        created: list[AgentJobStep] = []
        for index, item in enumerate(steps, start=1):
            step = AgentJobStep(
                job_id=job_id,
                step_kind=str(item["step_kind"]),
                status=AgentStepStatus.PENDING.value,
                step_order=index,
                target_file_id=item.get("target_file_id"),
                input_json=item.get("input_json"),
            )
            session.add(step)
            created.append(step)
        await session.flush()
        payload = [_step_to_dict(step) for step in created]
        await session.commit()
        return payload


async def get_agent_job(job_id: int) -> dict[str, Any] | None:
    async with async_session_factory() as session:
        result = await session.execute(select(AgentJob).where(AgentJob.id == job_id))
        job = result.scalar_one_or_none()
        return None if job is None else _job_to_dict(job)


async def list_agent_job_steps(job_id: int) -> list[dict[str, Any]]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(AgentJobStep)
            .where(AgentJobStep.job_id == job_id)
            .order_by(AgentJobStep.step_order.asc(), AgentJobStep.id.asc())
        )
        return [_step_to_dict(step) for step in result.scalars().all()]


async def mark_job_running(job_id: int) -> None:
    async with async_session_factory() as session:
        job = await session.get(AgentJob, job_id)
        if job is None:
            raise LookupError(f"Agent job {job_id} not found.")
        job.status = AgentJobStatus.RUNNING.value
        job.started_at = _get_now()
        await session.commit()


async def mark_job_completed(job_id: int, result_status: str) -> None:
    async with async_session_factory() as session:
        job = await session.get(AgentJob, job_id)
        if job is None:
            raise LookupError(f"Agent job {job_id} not found.")
        job.status = result_status
        job.finished_at = _get_now()
        await session.commit()


async def mark_job_failed(job_id: int, error_message: str) -> None:
    async with async_session_factory() as session:
        job = await session.get(AgentJob, job_id)
        if job is None:
            raise LookupError(f"Agent job {job_id} not found.")
        job.status = AgentJobStatus.FAILED.value
        job.error_message = error_message
        job.finished_at = _get_now()
        await session.commit()


async def mark_step_running(step_id: int) -> None:
    async with async_session_factory() as session:
        step = await session.get(AgentJobStep, step_id)
        if step is None:
            raise LookupError(f"Agent step {step_id} not found.")
        step.status = AgentStepStatus.RUNNING.value
        step.started_at = _get_now()
        await session.commit()


async def mark_step_completed(step_id: int, result_json: dict[str, object]) -> None:
    async with async_session_factory() as session:
        step = await session.get(AgentJobStep, step_id)
        if step is None:
            raise LookupError(f"Agent step {step_id} not found.")
        step.status = AgentStepStatus.COMPLETED.value
        step.result_json = result_json
        step.finished_at = _get_now()
        await session.commit()


async def mark_step_skipped(step_id: int, result_json: dict[str, object]) -> None:
    async with async_session_factory() as session:
        step = await session.get(AgentJobStep, step_id)
        if step is None:
            raise LookupError(f"Agent step {step_id} not found.")
        step.status = AgentStepStatus.SKIPPED.value
        step.result_json = result_json
        step.finished_at = _get_now()
        await session.commit()


async def mark_step_failed(step_id: int, error_message: str) -> None:
    async with async_session_factory() as session:
        step = await session.get(AgentJobStep, step_id)
        if step is None:
            raise LookupError(f"Agent step {step_id} not found.")
        step.status = AgentStepStatus.FAILED.value
        step.error_message = error_message
        step.finished_at = _get_now()
        await session.commit()