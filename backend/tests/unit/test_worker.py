"""Unit tests for WorkerRegistry, WorkerContext isolation, and capability bounds."""

from app.memory.schemas import MemoryType
from app.orchestration.schemas import DelegatedTask, WorkerType
from app.orchestration.worker import WorkerContext, WorkerRegistry


def test_worker_registry_defaults_and_constraints() -> None:
    registry = WorkerRegistry()

    # Research Worker: allowed search tools, episodic/semantic memory
    research_worker = registry.get_by_type(WorkerType.RESEARCH)
    assert "search_memory" in research_worker.allowed_tools
    assert MemoryType.EPISODIC in research_worker.allowed_memory_types

    # Analysis Worker: calculator tool
    analysis_worker = registry.get_by_type(WorkerType.ANALYSIS)
    assert "calculator" in analysis_worker.allowed_tools

    # Synthesis Worker: STRICTLY NO tools
    synthesis_worker = registry.get_by_type(WorkerType.SYNTHESIS)
    assert len(synthesis_worker.allowed_tools) == 0


def test_worker_context_prompt_defense_isolation() -> None:
    task = DelegatedTask(
        delegated_task_id="task_01",
        worker_id="worker_analysis",
        title="Arithmetic Calculation",
        objective="Calculate 10 + 20",
        input_context={"param": "value"},
    )

    dep_outputs = {"task_research": "Fact: 10 + 20 is an addition problem"}
    memories = [{"id": "mem-1", "content": "Previous addition example"}]

    prompt = WorkerContext.build_worker_objective(
        task=task,
        dependency_outputs=dep_outputs,
        relevant_memory=memories,
    )

    assert "### WORKER OBJECTIVE (TASK: Arithmetic Calculation)" in prompt
    assert "=== BEGIN APPROVED INPUT CONTEXT (UNTRUSTED DATA) ===" in prompt
    assert "=== BEGIN DEPENDENCY DATA FROM PREVIOUS WORKERS (UNTRUSTED DATA) ===" in prompt
    assert "=== BEGIN RETRIEVED EPISODIC/SEMANTIC MEMORY (UNTRUSTED DATA) ===" in prompt
    assert "--- Output from Dependency [task_research] ---" in prompt
