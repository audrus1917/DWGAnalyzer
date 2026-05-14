import asyncio

from parsedwg.agent_runner import AgentRunner


def test_run_job_executes_steps_via_langgraph(monkeypatch) -> None:
    events: list[tuple[str, object]] = []

    async def fake_get_agent_job(job_id: int) -> dict[str, object] | None:
        assert job_id == 17
        return {"id": job_id, "status": "pending"}

    async def fake_list_agent_job_steps(job_id: int) -> list[dict[str, object]]:
        assert job_id == 17
        return [
            {
                "id": 101,
                "step_kind": "interpret_blocks",
                "step_order": 1,
                "status": "pending",
                "input_json": {"file_ref": "sample.dxf", "by_path": True, "project_name": None},
            },
            {
                "id": 102,
                "step_kind": "categorize_entities",
                "step_order": 2,
                "status": "pending",
                "input_json": {"file_ref": "sample.dxf", "by_path": True, "entity_type": "BLOCK"},
            },
        ]

    async def fake_mark_job_running(job_id: int) -> None:
        events.append(("job_running", job_id))

    async def fake_mark_job_completed(job_id: int, status: str) -> None:
        events.append(("job_completed", (job_id, status)))

    async def fake_mark_job_failed(job_id: int, message: str) -> None:
        events.append(("job_failed", (job_id, message)))

    async def fake_mark_step_running(step_id: int) -> None:
        events.append(("step_running", step_id))

    async def fake_mark_step_completed(step_id: int, result_json: dict[str, object]) -> None:
        events.append(("step_completed", (step_id, result_json["status"])))

    async def fake_mark_step_skipped(step_id: int, result_json: dict[str, object]) -> None:
        events.append(("step_skipped", (step_id, result_json["status"])))

    async def fake_mark_step_failed(step_id: int, message: str) -> None:
        events.append(("step_failed", (step_id, message)))

    async def fake_run_step(_self, step_kind: str, input_json: dict[str, object]) -> dict[str, object]:
        _ = _self
        if step_kind == "interpret_blocks":
            assert input_json["file_ref"] == "sample.dxf"
            return {"status": "completed", "processed": 1}
        assert step_kind == "categorize_entities"
        return {"status": "skipped", "reason": "nothing to do"}

    start_node = "__start__"
    end_node = "__end__"

    class FakeCompiledGraph:
        def __init__(
            self,
            nodes: dict[str, object],
            edges: dict[str, str],
            routers: dict[str, tuple[object, dict[str, str]]],
        ) -> None:
            self._nodes = nodes
            self._edges = edges
            self._routers = routers

        async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
            node_name = self._edges[start_node]
            current_state = state
            while node_name != end_node:
                current_state = await self._nodes[node_name](current_state)
                if node_name in self._routers:
                    router, mapping = self._routers[node_name]
                    node_name = mapping[router(current_state)]
                else:
                    node_name = self._edges[node_name]
            return current_state

    class FakeStateGraph:
        def __init__(self, _state_type: object) -> None:
            self._nodes: dict[str, object] = {}
            self._edges: dict[str, str] = {}
            self._routers: dict[str, tuple[object, dict[str, str]]] = {}

        def add_node(self, name: str, node: object) -> None:
            self._nodes[name] = node

        def add_edge(self, source: str, target: str) -> None:
            self._edges[source] = target

        def add_conditional_edges(
            self,
            source: str,
            router: object,
            mapping: dict[str, str],
        ) -> None:
            self._routers[source] = (router, mapping)

        def compile(self) -> FakeCompiledGraph:
            return FakeCompiledGraph(self._nodes, self._edges, self._routers)

    monkeypatch.setattr("parsedwg.agent_runner.get_agent_job", fake_get_agent_job)
    monkeypatch.setattr("parsedwg.agent_runner.list_agent_job_steps", fake_list_agent_job_steps)
    monkeypatch.setattr("parsedwg.agent_runner.mark_job_running", fake_mark_job_running)
    monkeypatch.setattr("parsedwg.agent_runner.mark_job_completed", fake_mark_job_completed)
    monkeypatch.setattr("parsedwg.agent_runner.mark_job_failed", fake_mark_job_failed)
    monkeypatch.setattr("parsedwg.agent_runner.mark_step_running", fake_mark_step_running)
    monkeypatch.setattr("parsedwg.agent_runner.mark_step_completed", fake_mark_step_completed)
    monkeypatch.setattr("parsedwg.agent_runner.mark_step_skipped", fake_mark_step_skipped)
    monkeypatch.setattr("parsedwg.agent_runner.mark_step_failed", fake_mark_step_failed)
    monkeypatch.setattr(AgentRunner, "run_step", fake_run_step)
    monkeypatch.setattr(
        AgentRunner,
        "_get_langgraph_primitives",
        staticmethod(lambda: (start_node, end_node, FakeStateGraph)),
    )

    runner = AgentRunner(
        ai_model="model",
        ai_base_url="http://localhost:11434/v1",
        ai_api_key="",
        workers=1,
        dry=False,
    )

    summary = asyncio.run(runner.run_job(17))

    assert summary == {
        "job_id": 17,
        "steps_total": 2,
        "steps_completed": 0,
        "steps_failed": 0,
        "steps_skipped": 0,
    }
    assert events == [
        ("job_running", 17),
        ("step_running", 101),
        ("step_completed", (101, "completed")),
        ("step_running", 102),
        ("step_skipped", (102, "skipped")),
        ("job_completed", (17, "completed")),
    ]


def test_run_job_skips_categorize_when_interpret_found_nothing(monkeypatch) -> None:
    events: list[tuple[str, object]] = []

    async def fake_get_agent_job(job_id: int) -> dict[str, object] | None:
        assert job_id == 17
        return {"id": job_id, "status": "pending"}

    async def fake_list_agent_job_steps(job_id: int) -> list[dict[str, object]]:
        assert job_id == 17
        return [
            {
                "id": 101,
                "step_kind": "interpret_blocks",
                "step_order": 1,
                "status": "pending",
                "input_json": {"file_ref": "sample.dxf", "by_path": True, "project_name": None},
            },
            {
                "id": 102,
                "step_kind": "categorize_entities",
                "step_order": 2,
                "status": "pending",
                "input_json": {"file_ref": "sample.dxf", "by_path": True, "entity_type": "BLOCK"},
            },
        ]

    async def fake_mark_job_running(job_id: int) -> None:
        events.append(("job_running", job_id))

    async def fake_mark_job_completed(job_id: int, status: str) -> None:
        events.append(("job_completed", (job_id, status)))

    async def fake_mark_step_running(step_id: int) -> None:
        events.append(("step_running", step_id))

    async def fake_mark_step_completed(step_id: int, result_json: dict[str, object]) -> None:
        events.append(("step_completed", (step_id, result_json["status"])))

    async def fake_mark_step_skipped(step_id: int, result_json: dict[str, object]) -> None:
        events.append(("step_skipped", (step_id, result_json["reason"])))

    async def fake_mark_step_failed(step_id: int, message: str) -> None:
        events.append(("step_failed", (step_id, message)))

    async def fake_mark_job_failed(job_id: int, message: str) -> None:
        events.append(("job_failed", (job_id, message)))

    async def fake_run_step(_self, step_kind: str, input_json: dict[str, object]) -> dict[str, object]:
        _ = (_self, input_json)
        assert step_kind == "interpret_blocks"
        return {
            "status": "completed",
            "processed": 0,
            "failed": 0,
            "saved": 0,
        }

    start_node = "__start__"
    end_node = "__end__"

    class FakeCompiledGraph:
        def __init__(
            self,
            nodes: dict[str, object],
            edges: dict[str, str],
            routers: dict[str, tuple[object, dict[str, str]]],
        ) -> None:
            self._nodes = nodes
            self._edges = edges
            self._routers = routers

        async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
            node_name = self._edges[start_node]
            current_state = state
            while node_name != end_node:
                current_state = await self._nodes[node_name](current_state)
                if node_name in self._routers:
                    router, mapping = self._routers[node_name]
                    node_name = mapping[router(current_state)]
                else:
                    node_name = self._edges[node_name]
            return current_state

    class FakeStateGraph:
        def __init__(self, _state_type: object) -> None:
            self._nodes: dict[str, object] = {}
            self._edges: dict[str, str] = {}
            self._routers: dict[str, tuple[object, dict[str, str]]] = {}

        def add_node(self, name: str, node: object) -> None:
            self._nodes[name] = node

        def add_edge(self, source: str, target: str) -> None:
            self._edges[source] = target

        def add_conditional_edges(
            self,
            source: str,
            router: object,
            mapping: dict[str, str],
        ) -> None:
            self._routers[source] = (router, mapping)

        def compile(self) -> FakeCompiledGraph:
            return FakeCompiledGraph(self._nodes, self._edges, self._routers)

    monkeypatch.setattr("parsedwg.agent_runner.get_agent_job", fake_get_agent_job)
    monkeypatch.setattr("parsedwg.agent_runner.list_agent_job_steps", fake_list_agent_job_steps)
    monkeypatch.setattr("parsedwg.agent_runner.mark_job_running", fake_mark_job_running)
    monkeypatch.setattr("parsedwg.agent_runner.mark_job_completed", fake_mark_job_completed)
    monkeypatch.setattr("parsedwg.agent_runner.mark_job_failed", fake_mark_job_failed)
    monkeypatch.setattr("parsedwg.agent_runner.mark_step_running", fake_mark_step_running)
    monkeypatch.setattr("parsedwg.agent_runner.mark_step_completed", fake_mark_step_completed)
    monkeypatch.setattr("parsedwg.agent_runner.mark_step_skipped", fake_mark_step_skipped)
    monkeypatch.setattr("parsedwg.agent_runner.mark_step_failed", fake_mark_step_failed)
    monkeypatch.setattr(AgentRunner, "run_step", fake_run_step)
    monkeypatch.setattr(
        AgentRunner,
        "_get_langgraph_primitives",
        staticmethod(lambda: (start_node, end_node, FakeStateGraph)),
    )

    runner = AgentRunner(
        ai_model="model",
        ai_base_url="http://localhost:11434/v1",
        ai_api_key="",
        workers=1,
        dry=False,
    )

    asyncio.run(runner.run_job(17))

    assert events == [
        ("job_running", 17),
        ("step_running", 101),
        ("step_completed", (101, "completed")),
        (
            "step_skipped",
            (
                102,
                "categorize_entities пропущен: предыдущий interpret_blocks не нашёл сущностей для обработки.",
            ),
        ),
        ("job_completed", (17, "completed")),
    ]


def test_run_job_raises_clear_error_when_langgraph_missing(monkeypatch) -> None:
    async def fake_get_agent_job(job_id: int) -> dict[str, object] | None:
        return {"id": job_id}

    async def fake_list_agent_job_steps(_job_id: int) -> list[dict[str, object]]:
        _ = _job_id
        return []

    async def fake_mark_job_running(job_id: int) -> None:
        _ = job_id

    async def fake_mark_job_failed(job_id: int, message: str) -> None:
        assert job_id == 17
        assert "LangGraph" in message

    monkeypatch.setattr("parsedwg.agent_runner.get_agent_job", fake_get_agent_job)
    monkeypatch.setattr("parsedwg.agent_runner.list_agent_job_steps", fake_list_agent_job_steps)
    monkeypatch.setattr("parsedwg.agent_runner.mark_job_running", fake_mark_job_running)
    monkeypatch.setattr("parsedwg.agent_runner.mark_job_failed", fake_mark_job_failed)
    monkeypatch.setattr(
        AgentRunner,
        "_get_langgraph_primitives",
        staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("LangGraph missing"))),
    )

    runner = AgentRunner(
        ai_model="model",
        ai_base_url="http://localhost:11434/v1",
        ai_api_key="",
        workers=1,
        dry=False,
    )

    try:
        asyncio.run(runner.run_job(17))
    except RuntimeError as exc:
        assert str(exc) == "LangGraph missing"
    else:
        raise AssertionError("Expected RuntimeError when LangGraph is unavailable")


def test_run_job_skips_verify_when_categorize_found_nothing(monkeypatch) -> None:
    events: list[tuple[str, object]] = []

    async def fake_get_agent_job(job_id: int) -> dict[str, object] | None:
        assert job_id == 17
        return {"id": job_id, "status": "pending"}

    async def fake_list_agent_job_steps(job_id: int) -> list[dict[str, object]]:
        assert job_id == 17
        return [
            {
                "id": 101,
                "step_kind": "interpret_blocks",
                "step_order": 1,
                "status": "pending",
                "input_json": {"file_ref": "sample.dxf", "by_path": True, "project_name": None},
            },
            {
                "id": 102,
                "step_kind": "categorize_entities",
                "step_order": 2,
                "status": "pending",
                "input_json": {"file_ref": "sample.dxf", "by_path": True, "entity_type": "BLOCK"},
            },
            {
                "id": 103,
                "step_kind": "verify_extraction",
                "step_order": 3,
                "status": "pending",
                "input_json": {"drawing_path": "sample.dxf", "file_id": None},
            },
        ]

    async def fake_mark_job_running(job_id: int) -> None:
        events.append(("job_running", job_id))

    async def fake_mark_job_completed(job_id: int, status: str) -> None:
        events.append(("job_completed", (job_id, status)))

    async def fake_mark_step_running(step_id: int) -> None:
        events.append(("step_running", step_id))

    async def fake_mark_step_completed(step_id: int, result_json: dict[str, object]) -> None:
        events.append(("step_completed", (step_id, result_json["status"])))

    async def fake_mark_step_skipped(step_id: int, result_json: dict[str, object]) -> None:
        events.append(("step_skipped", (step_id, result_json["reason"])))

    async def fake_mark_step_failed(step_id: int, message: str) -> None:
        events.append(("step_failed", (step_id, message)))

    async def fake_mark_job_failed(job_id: int, message: str) -> None:
        events.append(("job_failed", (job_id, message)))

    async def fake_run_step(_self, step_kind: str, input_json: dict[str, object]) -> dict[str, object]:
        _ = (_self, input_json)
        if step_kind == "interpret_blocks":
            return {
                "status": "completed",
                "processed": 2,
                "failed": 0,
                "saved": 2,
            }
        assert step_kind == "categorize_entities"
        return {
            "status": "completed",
            "processed": 0,
            "failed": 0,
            "saved": 0,
        }

    start_node = "__start__"
    end_node = "__end__"

    class FakeCompiledGraph:
        def __init__(
            self,
            nodes: dict[str, object],
            edges: dict[str, str],
            routers: dict[str, tuple[object, dict[str, str]]],
        ) -> None:
            self._nodes = nodes
            self._edges = edges
            self._routers = routers

        async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
            node_name = self._edges[start_node]
            current_state = state
            while node_name != end_node:
                current_state = await self._nodes[node_name](current_state)
                if node_name in self._routers:
                    router, mapping = self._routers[node_name]
                    node_name = mapping[router(current_state)]
                else:
                    node_name = self._edges[node_name]
            return current_state

    class FakeStateGraph:
        def __init__(self, _state_type: object) -> None:
            self._nodes: dict[str, object] = {}
            self._edges: dict[str, str] = {}
            self._routers: dict[str, tuple[object, dict[str, str]]] = {}

        def add_node(self, name: str, node: object) -> None:
            self._nodes[name] = node

        def add_edge(self, source: str, target: str) -> None:
            self._edges[source] = target

        def add_conditional_edges(
            self,
            source: str,
            router: object,
            mapping: dict[str, str],
        ) -> None:
            self._routers[source] = (router, mapping)

        def compile(self) -> FakeCompiledGraph:
            return FakeCompiledGraph(self._nodes, self._edges, self._routers)

    monkeypatch.setattr("parsedwg.agent_runner.get_agent_job", fake_get_agent_job)
    monkeypatch.setattr("parsedwg.agent_runner.list_agent_job_steps", fake_list_agent_job_steps)
    monkeypatch.setattr("parsedwg.agent_runner.mark_job_running", fake_mark_job_running)
    monkeypatch.setattr("parsedwg.agent_runner.mark_job_completed", fake_mark_job_completed)
    monkeypatch.setattr("parsedwg.agent_runner.mark_job_failed", fake_mark_job_failed)
    monkeypatch.setattr("parsedwg.agent_runner.mark_step_running", fake_mark_step_running)
    monkeypatch.setattr("parsedwg.agent_runner.mark_step_completed", fake_mark_step_completed)
    monkeypatch.setattr("parsedwg.agent_runner.mark_step_skipped", fake_mark_step_skipped)
    monkeypatch.setattr("parsedwg.agent_runner.mark_step_failed", fake_mark_step_failed)
    monkeypatch.setattr(AgentRunner, "run_step", fake_run_step)
    monkeypatch.setattr(
        AgentRunner,
        "_get_langgraph_primitives",
        staticmethod(lambda: (start_node, end_node, FakeStateGraph)),
    )

    runner = AgentRunner(
        ai_model="model",
        ai_base_url="http://localhost:11434/v1",
        ai_api_key="",
        workers=1,
        dry=False,
    )

    asyncio.run(runner.run_job(17))

    assert events == [
        ("job_running", 17),
        ("step_running", 101),
        ("step_completed", (101, "completed")),
        ("step_running", 102),
        ("step_completed", (102, "completed")),
        (
            "step_skipped",
            (
                103,
                "verify_extraction пропущен: предыдущий categorize_entities не обработал ни одной сущности.",
            ),
        ),
        ("job_completed", (17, "completed")),
    ]


def test_run_job_skips_verify_when_profile_is_not_full(monkeypatch) -> None:
    events: list[tuple[str, object]] = []

    async def fake_get_agent_job(job_id: int) -> dict[str, object] | None:
        assert job_id == 17
        return {"id": job_id, "status": "pending", "profile": "interpret-only"}

    async def fake_list_agent_job_steps(job_id: int) -> list[dict[str, object]]:
        assert job_id == 17
        return [
            {
                "id": 103,
                "step_kind": "verify_extraction",
                "step_order": 1,
                "status": "pending",
                "input_json": {"drawing_path": "sample.dxf", "file_id": None},
            }
        ]

    async def fake_mark_job_running(job_id: int) -> None:
        events.append(("job_running", job_id))

    async def fake_mark_job_completed(job_id: int, status: str) -> None:
        events.append(("job_completed", (job_id, status)))

    async def fake_mark_step_skipped(step_id: int, result_json: dict[str, object]) -> None:
        events.append(("step_skipped", (step_id, result_json["reason"])))

    async def fake_mark_job_failed(job_id: int, message: str) -> None:
        events.append(("job_failed", (job_id, message)))

    start_node = "__start__"
    end_node = "__end__"

    class FakeCompiledGraph:
        def __init__(
            self,
            nodes: dict[str, object],
            edges: dict[str, str],
            routers: dict[str, tuple[object, dict[str, str]]],
        ) -> None:
            self._nodes = nodes
            self._edges = edges
            self._routers = routers

        async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
            node_name = self._edges[start_node]
            current_state = state
            while node_name != end_node:
                current_state = await self._nodes[node_name](current_state)
                if node_name in self._routers:
                    router, mapping = self._routers[node_name]
                    node_name = mapping[router(current_state)]
                else:
                    node_name = self._edges[node_name]
            return current_state

    class FakeStateGraph:
        def __init__(self, _state_type: object) -> None:
            self._nodes: dict[str, object] = {}
            self._edges: dict[str, str] = {}
            self._routers: dict[str, tuple[object, dict[str, str]]] = {}

        def add_node(self, name: str, node: object) -> None:
            self._nodes[name] = node

        def add_edge(self, source: str, target: str) -> None:
            self._edges[source] = target

        def add_conditional_edges(
            self,
            source: str,
            router: object,
            mapping: dict[str, str],
        ) -> None:
            self._routers[source] = (router, mapping)

        def compile(self) -> FakeCompiledGraph:
            return FakeCompiledGraph(self._nodes, self._edges, self._routers)

    monkeypatch.setattr("parsedwg.agent_runner.get_agent_job", fake_get_agent_job)
    monkeypatch.setattr("parsedwg.agent_runner.list_agent_job_steps", fake_list_agent_job_steps)
    monkeypatch.setattr("parsedwg.agent_runner.mark_job_running", fake_mark_job_running)
    monkeypatch.setattr("parsedwg.agent_runner.mark_job_completed", fake_mark_job_completed)
    monkeypatch.setattr("parsedwg.agent_runner.mark_job_failed", fake_mark_job_failed)
    monkeypatch.setattr("parsedwg.agent_runner.mark_step_skipped", fake_mark_step_skipped)
    monkeypatch.setattr(
        AgentRunner,
        "_get_langgraph_primitives",
        staticmethod(lambda: (start_node, end_node, FakeStateGraph)),
    )

    runner = AgentRunner(
        ai_model="model",
        ai_base_url="http://localhost:11434/v1",
        ai_api_key="",
        workers=1,
        dry=False,
    )

    asyncio.run(runner.run_job(17))

    assert events == [
        ("job_running", 17),
        (
            "step_skipped",
            (
                103,
                "verify_extraction пропущен: профиль запуска не поддерживает шаг проверки.",
            ),
        ),
        ("job_completed", (17, "completed")),
    ]


def test_run_job_skips_verify_when_dry_run_enabled(monkeypatch) -> None:
    events: list[tuple[str, object]] = []

    async def fake_get_agent_job(job_id: int) -> dict[str, object] | None:
        assert job_id == 17
        return {
            "id": job_id,
            "status": "pending",
            "profile": "full",
            "options_json": {"dry": True},
        }

    async def fake_list_agent_job_steps(job_id: int) -> list[dict[str, object]]:
        assert job_id == 17
        return [
            {
                "id": 103,
                "step_kind": "verify_extraction",
                "step_order": 1,
                "status": "pending",
                "input_json": {"drawing_path": "sample.dxf", "file_id": None},
            }
        ]

    async def fake_mark_job_running(job_id: int) -> None:
        events.append(("job_running", job_id))

    async def fake_mark_job_completed(job_id: int, status: str) -> None:
        events.append(("job_completed", (job_id, status)))

    async def fake_mark_step_skipped(step_id: int, result_json: dict[str, object]) -> None:
        events.append(("step_skipped", (step_id, result_json["reason"])))

    async def fake_mark_job_failed(job_id: int, message: str) -> None:
        events.append(("job_failed", (job_id, message)))

    start_node = "__start__"
    end_node = "__end__"

    class FakeCompiledGraph:
        def __init__(
            self,
            nodes: dict[str, object],
            edges: dict[str, str],
            routers: dict[str, tuple[object, dict[str, str]]],
        ) -> None:
            self._nodes = nodes
            self._edges = edges
            self._routers = routers

        async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
            node_name = self._edges[start_node]
            current_state = state
            while node_name != end_node:
                current_state = await self._nodes[node_name](current_state)
                if node_name in self._routers:
                    router, mapping = self._routers[node_name]
                    node_name = mapping[router(current_state)]
                else:
                    node_name = self._edges[node_name]
            return current_state

    class FakeStateGraph:
        def __init__(self, _state_type: object) -> None:
            self._nodes: dict[str, object] = {}
            self._edges: dict[str, str] = {}
            self._routers: dict[str, tuple[object, dict[str, str]]] = {}

        def add_node(self, name: str, node: object) -> None:
            self._nodes[name] = node

        def add_edge(self, source: str, target: str) -> None:
            self._edges[source] = target

        def add_conditional_edges(
            self,
            source: str,
            router: object,
            mapping: dict[str, str],
        ) -> None:
            self._routers[source] = (router, mapping)

        def compile(self) -> FakeCompiledGraph:
            return FakeCompiledGraph(self._nodes, self._edges, self._routers)

    monkeypatch.setattr("parsedwg.agent_runner.get_agent_job", fake_get_agent_job)
    monkeypatch.setattr("parsedwg.agent_runner.list_agent_job_steps", fake_list_agent_job_steps)
    monkeypatch.setattr("parsedwg.agent_runner.mark_job_running", fake_mark_job_running)
    monkeypatch.setattr("parsedwg.agent_runner.mark_job_completed", fake_mark_job_completed)
    monkeypatch.setattr("parsedwg.agent_runner.mark_job_failed", fake_mark_job_failed)
    monkeypatch.setattr("parsedwg.agent_runner.mark_step_skipped", fake_mark_step_skipped)
    monkeypatch.setattr(
        AgentRunner,
        "_get_langgraph_primitives",
        staticmethod(lambda: (start_node, end_node, FakeStateGraph)),
    )

    runner = AgentRunner(
        ai_model="model",
        ai_base_url="http://localhost:11434/v1",
        ai_api_key="",
        workers=1,
        dry=False,
    )

    asyncio.run(runner.run_job(17))

    assert events == [
        ("job_running", 17),
        (
            "step_skipped",
            (
                103,
                "verify_extraction пропущен: dry-run не формирует устойчивое состояние для проверки результатов.",
            ),
        ),
        ("job_completed", (17, "completed")),
    ]