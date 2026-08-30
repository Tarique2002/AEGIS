"""Unit tests for OrchestrationBudgetState and hierarchical budget bounds."""

from app.orchestration.policies import OrchestrationPolicy
from app.orchestration.schemas import OrchestrationBudgetState


def test_budget_state_tracking() -> None:
    budget = OrchestrationBudgetState()
    assert budget.worker_count == 0
    assert budget.completed_workers == 0
    assert budget.total_iterations == 0

    budget.worker_count = 3
    budget.active_workers += 1
    budget.total_iterations += 2
    budget.total_tool_calls += 3
    budget.elapsed_time_ms += 150.0

    assert budget.active_workers == 1
    assert budget.total_iterations == 2
    assert budget.total_tool_calls == 3
    assert budget.elapsed_time_ms == 150.0


def test_orchestration_policy_bounds() -> None:
    policy = OrchestrationPolicy(
        max_workers=6,
        max_parallel_workers=3,
        max_total_iterations=20,
        max_total_tool_calls=60,
    )
    assert policy.max_workers == 6
    assert policy.max_parallel_workers == 3
    assert policy.max_total_iterations == 20
    assert policy.max_total_tool_calls == 60
