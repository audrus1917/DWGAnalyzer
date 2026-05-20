"""Orchestrator for the agent pipeline."""

from __future__ import annotations

import importlib
import logging

from pathlib import Path
from typing import Any, TypedDict

from src.parsedwg.settings import settings
from src.parsedwg.ai.agent_db import (
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
from src.parsedwg.ai.agent_planner import AgentGraphPlanner
from src.parsedwg.ai.agent_types import AgentJobStatus, AgentProfile, AgentStepKind
from src.parsedwg.ai.agent_workers import (
    run_categorize_entities_step,
    run_interpret_blocks_step,
    run_verify_extraction_step,
)

logger = logging.getLogger(__name__)


class _AgentGraphState(TypedDict):
    job_id: int
    steps: list[dict[str, object]]
    next_step_index: int
    current_step: dict[str, object] | None
    job_profile: str
    dry_run: bool
    last_step_kind: str | None
    last_step_result: dict[str, object] | None
    planned_route: str | None
    planned_reason: str | None


class AgentRunner:
    def __init__(
        self,
        workers: int,
        dry: bool,
        project_name: str | None = None,
    ) -> None:
        self.ai_model = settings.ai_model
        self.ai_base_url = settings.ai_base_url
        self.ai_api_key = settings.ai_api_key
        self.workers = workers
        self.dry = dry
        self.project_name = project_name
        self.planner = AgentGraphPlanner()

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
        logger.debug(f"Creating agent job for input_ref={input_ref} with profile={profile}")
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
        raw_profile = job.get("profile") if isinstance(job, dict) else None
        job_profile = str(raw_profile or "")
        raw_options = job.get("options_json") if isinstance(job, dict) else None
        dry_run = self.dry
        if isinstance(raw_options, dict) and isinstance(raw_options.get("dry"), bool):
            dry_run = raw_options["dry"]

        await mark_job_running(job_id)
        steps = await list_agent_job_steps(job_id)
        try:
            graph = self._build_execution_graph()
            await graph.ainvoke(
                {
                    "job_id": job_id,
                    "steps": steps,
                    "next_step_index": 0,
                    "current_step": None,
                    "job_profile": job_profile,
                    "dry_run": dry_run,
                    "last_step_kind": None,
                    "last_step_result": None,
                    "planned_route": None,
                    "planned_reason": None,
                }
            )
            await mark_job_completed(job_id, AgentJobStatus.COMPLETED.value)
        except Exception as exc:
            await mark_job_failed(job_id, str(exc))
            raise

        updated_steps = await list_agent_job_steps(job_id)
        return self.build_summary(job_id, updated_steps)

    def _build_execution_graph(self) -> Any:
        start_node, end_node, state_graph = self._get_langgraph_primitives()
        graph = state_graph(_AgentGraphState)

        dispatch_node = "dispatch_step"
        graph.add_node(dispatch_node, self._dispatch_step)
        graph.add_node("skip_step", self._skip_current_step)
        graph.add_node(
            AgentStepKind.INTERPRET_BLOCKS.value,
            self._make_step_kind_node(AgentStepKind.INTERPRET_BLOCKS.value),
        )
        graph.add_node(
            AgentStepKind.CATEGORIZE_ENTITIES.value,
            self._make_step_kind_node(AgentStepKind.CATEGORIZE_ENTITIES.value),
        )
        graph.add_node(
            AgentStepKind.VERIFY_EXTRACTION.value,
            self._make_step_kind_node(AgentStepKind.VERIFY_EXTRACTION.value),
        )

        graph.add_edge(start_node, dispatch_node)
        graph.add_conditional_edges(
            dispatch_node,
            self._route_current_step,
            {
                AgentStepKind.INTERPRET_BLOCKS.value: AgentStepKind.INTERPRET_BLOCKS.value,
                AgentStepKind.CATEGORIZE_ENTITIES.value: AgentStepKind.CATEGORIZE_ENTITIES.value,
                AgentStepKind.VERIFY_EXTRACTION.value: AgentStepKind.VERIFY_EXTRACTION.value,
                "skip_step": "skip_step",
                "end": end_node,
            },
        )
        graph.add_edge("skip_step", dispatch_node)
        graph.add_edge(AgentStepKind.INTERPRET_BLOCKS.value, dispatch_node)
        graph.add_edge(AgentStepKind.CATEGORIZE_ENTITIES.value, dispatch_node)
        graph.add_edge(AgentStepKind.VERIFY_EXTRACTION.value, dispatch_node)
        return graph.compile()

    async def _dispatch_step(self, state: _AgentGraphState) -> _AgentGraphState:
        steps = state["steps"]
        next_step_index = state["next_step_index"]
        current_step = steps[next_step_index] if next_step_index < len(steps) else None
        decision = self.planner.decide_next_route(
            {
                **state,
                "current_step": current_step,
            }
        )
        return {
            **state,
            "current_step": current_step,
            "planned_route": decision.route,
            "planned_reason": decision.reason,
        }

    def _route_current_step(self, state: _AgentGraphState) -> str:
        planned_route = state.get("planned_route")
        return str(planned_route or "end")

    async def _skip_current_step(self, state: _AgentGraphState) -> _AgentGraphState:
        step = state.get("current_step")
        if step is None:
            return {
                **state,
                "planned_route": None,
                "planned_reason": None,
            }

        raw_step_id = step.get("id")
        if not isinstance(raw_step_id, (int, str)):
            raise ValueError(f"Invalid step id: {raw_step_id}")
        step_id = int(raw_step_id)
        step_kind = str(step.get("step_kind") or "")
        reason = str(state.get("planned_reason") or "Step skipped by the planner.")
        result: dict[str, object] = {
            "status": "skipped",
            "reason": reason,
        }
        await mark_step_skipped(step_id, result)
        return {
            **state,
            "next_step_index": state["next_step_index"] + 1,
            "current_step": None,
            "last_step_kind": step_kind,
            "last_step_result": result,
            "planned_route": None,
            "planned_reason": None,
        }

    def _make_step_kind_node(self, expected_step_kind: str) -> Any:
        async def _run(state: _AgentGraphState) -> _AgentGraphState:
            step = state.get("current_step")
            if step is None:
                return state

            actual_step_kind = str(step["step_kind"])
            raw_step_id = step.get("id")
            if not isinstance(raw_step_id, (int, str)):
                raise ValueError(f"Invalid step id: {raw_step_id}")
            step_id = int(raw_step_id)
            raw_input_json = step.get("input_json")
            input_json = raw_input_json if isinstance(raw_input_json, dict) else {}
            if actual_step_kind != expected_step_kind:
                raise ValueError(
                    f"Unexpected step kind {actual_step_kind} for node {expected_step_kind}"
                )

            await mark_step_running(step_id)
            try:
                result = await self.run_step(actual_step_kind, input_json)
            except Exception as exc:
                await mark_step_failed(step_id, str(exc))
                raise

            if result.get("status") == "skipped":
                await mark_step_skipped(step_id, result)
            else:
                await mark_step_completed(step_id, result)
            return {
                **state,
                "next_step_index": state["next_step_index"] + 1,
                "current_step": None,
                "last_step_kind": actual_step_kind,
                "last_step_result": result,
                "planned_route": None,
                "planned_reason": None,
            }

        return _run

    @staticmethod
    def _get_langgraph_primitives() -> tuple[object, object, Any]:
        try:
            graph_module = importlib.import_module("langgraph.graph")
        except ImportError as exc:
            raise RuntimeError(
                "To use agent-run via LangGraph, install the optional AI dependencies: "
                "parsedwg[ai] or the langgraph package."
            ) from exc

        return graph_module.START, graph_module.END, graph_module.StateGraph

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
                    "reason": "verify_extraction is supported only for a single file.",
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