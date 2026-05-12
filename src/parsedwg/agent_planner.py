"""Планировщик переходов для графа агентного пайплайна."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .agent_types import AgentStepKind


@dataclass(frozen=True)
class AgentGraphDecision:
    route: str
    reason: str | None = None


@dataclass(frozen=True)
class AgentGraphPolicy:
    route: str
    predicate: Callable[[Mapping[str, object]], bool]
    reason_builder: Callable[[Mapping[str, object]], str | None] | None = None

    def evaluate(self, state: Mapping[str, object]) -> AgentGraphDecision | None:
        if not self.predicate(state):
            return None
        reason = self.reason_builder(state) if self.reason_builder is not None else None
        return AgentGraphDecision(route=self.route, reason=reason)


class AgentGraphPlanner:
    """Определяет следующий переход графа на основе текущего шага и результатов ранее.

    Planner использует policy-таблицу переходов поверх текущего состояния графа.
    Сейчас поддержаны два result-aware правила:
    1. Если interpret_blocks не нашёл сущностей, skip для categorize_entities.
    2. Если categorize_entities не обработал ни одной сущности, skip для verify_extraction.
    """

    _SUPPORTED_ROUTES = {
        AgentStepKind.INTERPRET_BLOCKS.value,
        AgentStepKind.CATEGORIZE_ENTITIES.value,
        AgentStepKind.VERIFY_EXTRACTION.value,
        "skip_step",
        "end",
    }

    def __init__(self) -> None:
        self._policies: tuple[AgentGraphPolicy, ...] = (
            AgentGraphPolicy(
                route="skip_step",
                predicate=self._should_skip_verify_in_dry_run,
                reason_builder=lambda _state: (
                    "verify_extraction пропущен: dry-run не формирует устойчивое состояние "
                    "для проверки результатов."
                ),
            ),
            AgentGraphPolicy(
                route="skip_step",
                predicate=self._should_skip_verify_for_non_full_profile,
                reason_builder=lambda _state: (
                    "verify_extraction пропущен: профиль запуска не поддерживает шаг проверки."
                ),
            ),
            AgentGraphPolicy(
                route="skip_step",
                predicate=self._should_skip_categorize_after_empty_interpret,
                reason_builder=lambda _state: (
                    "categorize_entities пропущен: предыдущий interpret_blocks не нашёл "
                    "сущностей для обработки."
                ),
            ),
            AgentGraphPolicy(
                route="skip_step",
                predicate=self._should_skip_verify_after_empty_categorize,
                reason_builder=lambda _state: (
                    "verify_extraction пропущен: предыдущий categorize_entities не обработал "
                    "ни одной сущности."
                ),
            ),
        )

    def decide_next_route(self, state: Mapping[str, object]) -> AgentGraphDecision:
        current_step = state.get("current_step")
        if not isinstance(current_step, dict):
            return AgentGraphDecision(route="end")

        current_step_kind = str(current_step.get("step_kind") or "")

        for policy in self._policies:
            decision = policy.evaluate(state)
            if decision is not None:
                return decision

        if current_step_kind not in self._SUPPORTED_ROUTES:
            raise ValueError(f"Unsupported step kind: {current_step_kind}")
        return AgentGraphDecision(route=current_step_kind)

    def _should_skip_verify_in_dry_run(self, state: Mapping[str, object]) -> bool:
        return self._is_current_step(state, AgentStepKind.VERIFY_EXTRACTION.value) and bool(
            state.get("dry_run")
        )

    def _should_skip_verify_for_non_full_profile(self, state: Mapping[str, object]) -> bool:
        job_profile = state.get("job_profile")
        return self._is_current_step(
            state,
            AgentStepKind.VERIFY_EXTRACTION.value,
        ) and isinstance(job_profile, str) and job_profile != "" and job_profile != "full"

    def _should_skip_categorize_after_empty_interpret(self, state: Mapping[str, object]) -> bool:
        return self._is_current_step(
            state,
            AgentStepKind.CATEGORIZE_ENTITIES.value,
        ) and self._has_empty_step_result(
            state,
            expected_previous_kind=AgentStepKind.INTERPRET_BLOCKS.value,
        )

    def _should_skip_verify_after_empty_categorize(self, state: Mapping[str, object]) -> bool:
        return self._is_current_step(
            state,
            AgentStepKind.VERIFY_EXTRACTION.value,
        ) and self._has_empty_step_result(
            state,
            expected_previous_kind=AgentStepKind.CATEGORIZE_ENTITIES.value,
        )

    @staticmethod
    def _is_current_step(state: Mapping[str, object], expected_step_kind: str) -> bool:
        current_step = state.get("current_step")
        return isinstance(current_step, dict) and str(current_step.get("step_kind") or "") == expected_step_kind

    @staticmethod
    def _has_empty_step_result(
        state: Mapping[str, object],
        expected_previous_kind: str,
    ) -> bool:
        last_step_kind = state.get("last_step_kind")
        if last_step_kind != expected_previous_kind:
            return False

        last_step_result = state.get("last_step_result")
        if not isinstance(last_step_result, dict):
            return False

        processed = last_step_result.get("processed")
        failed = last_step_result.get("failed")
        saved = last_step_result.get("saved")

        return (
            isinstance(processed, int)
            and isinstance(failed, int)
            and failed == 0
            and processed == 0
            and (not isinstance(saved, int) or saved == 0)
        )