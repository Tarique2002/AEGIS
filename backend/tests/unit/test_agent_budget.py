"""Unit tests for AgentBudget manager and resource consumption thresholds."""

import pytest
from app.agent_loop.budget import AgentBudget
from app.agent_loop.errors import BudgetExceededError
from app.agent_loop.policies import AgentLoopPolicy


def test_budget_consumption_within_limits() -> None:
    policy = AgentLoopPolicy(max_iterations=5, max_tool_calls=10, max_llm_calls=5)
    budget = AgentBudget(policy=policy)

    budget.consume_iteration(2)
    budget.consume_tool_call(3)
    budget.consume_llm_call(2)
    budget.consume_retry(1)
    budget.consume_memory_read(2)
    budget.consume_memory_write(1)
    budget.consume_plan_execution(1)

    assert budget.state.iterations == 2
    assert budget.state.tool_calls == 3
    assert budget.state.llm_calls == 2

    remaining = budget.get_remaining_budget()
    assert remaining["iterations_remaining"] == 3
    assert remaining["tool_calls_remaining"] == 7
    assert remaining["llm_calls_remaining"] == 3


def test_budget_iteration_limit_exceeded() -> None:
    policy = AgentLoopPolicy(max_iterations=3)
    budget = AgentBudget(policy=policy)

    budget.consume_iteration(3)
    with pytest.raises(BudgetExceededError, match="Iteration limit exceeded"):
        budget.consume_iteration(1)


def test_budget_tool_calls_exceeded() -> None:
    policy = AgentLoopPolicy(max_tool_calls=2)
    budget = AgentBudget(policy=policy)

    budget.consume_tool_call(2)
    with pytest.raises(BudgetExceededError, match="Tool call budget exceeded"):
        budget.consume_tool_call(1)


def test_budget_time_limit_exceeded() -> None:
    policy = AgentLoopPolicy(max_total_execution_seconds=0.1)
    budget = AgentBudget(policy=policy)

    import time

    start_time = time.time() - 1.0  # 1 second ago

    with pytest.raises(BudgetExceededError, match="Execution time budget exceeded"):
        budget.check_time_limit(start_time)
