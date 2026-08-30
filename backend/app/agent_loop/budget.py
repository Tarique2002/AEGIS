"""Atomic resource budget manager enforcing cumulative limits on autonomous agent loops."""

import time
from typing import Any

from app.agent_loop.errors import BudgetExceededError
from app.agent_loop.policies import AgentLoopPolicy
from app.agent_loop.schemas import AgentBudgetState


class AgentBudget:
    """
    Tracks and atomically decrements/increments cumulative execution allowances.
    Raises BudgetExceededError immediately if any configured threshold is breached.
    """

    def __init__(
        self,
        policy: AgentLoopPolicy | None = None,
        state: AgentBudgetState | None = None,
    ) -> None:
        self.policy = policy or AgentLoopPolicy()
        self.state = state or AgentBudgetState()

    def consume_iteration(self, count: int = 1) -> None:
        """Register completed iteration count and check against policy limit."""
        if self.state.iterations + count > self.policy.max_iterations:
            raise BudgetExceededError(
                f"Iteration limit exceeded: {self.state.iterations + count} "
                f"> {self.policy.max_iterations}"
            )
        self.state.iterations += count

    def consume_tool_call(self, count: int = 1) -> None:
        """Register tool call count and check against policy limit."""
        if self.state.tool_calls + count > self.policy.max_tool_calls:
            raise BudgetExceededError(
                f"Tool call budget exceeded: {self.state.tool_calls + count} "
                f"> {self.policy.max_tool_calls}"
            )
        self.state.tool_calls += count

    def consume_llm_call(self, count: int = 1) -> None:
        """Register LLM call count and check against policy limit."""
        if self.state.llm_calls + count > self.policy.max_llm_calls:
            raise BudgetExceededError(
                f"LLM call budget exceeded: {self.state.llm_calls + count} "
                f"> {self.policy.max_llm_calls}"
            )
        self.state.llm_calls += count

    def consume_retry(self, count: int = 1) -> None:
        """Register retry count and check against policy limit."""
        if self.state.retries + count > self.policy.max_total_retries:
            raise BudgetExceededError(
                f"Retry budget exceeded: {self.state.retries + count} "
                f"> {self.policy.max_total_retries}"
            )
        self.state.retries += count

    def consume_memory_read(self, count: int = 1) -> None:
        """Register memory retrieval count and check against policy limit."""
        if self.state.memory_reads + count > self.policy.max_memory_retrievals:
            raise BudgetExceededError(
                f"Memory read budget exceeded: {self.state.memory_reads + count} "
                f"> {self.policy.max_memory_retrievals}"
            )
        self.state.memory_reads += count

    def consume_memory_write(self, count: int = 1) -> None:
        """Register memory write count and check against policy limit."""
        if self.state.memory_writes + count > self.policy.max_memory_writes:
            raise BudgetExceededError(
                f"Memory write budget exceeded: {self.state.memory_writes + count} "
                f"> {self.policy.max_memory_writes}"
            )
        self.state.memory_writes += count

    def consume_plan_execution(self, count: int = 1) -> None:
        """Register plan execution pass and check against policy limit."""
        if self.state.plan_executions + count > self.policy.max_plan_executions:
            raise BudgetExceededError(
                f"Plan execution budget exceeded: {self.state.plan_executions + count} "
                f"> {self.policy.max_plan_executions}"
            )
        self.state.plan_executions += count

    def record_elapsed_time(self, duration_ms: float) -> None:
        """Record additional elapsed wall-clock duration in milliseconds."""
        self.state.elapsed_time_ms += duration_ms

    def record_tokens(self, token_count: int) -> None:
        """Record tokens consumed by inference passes."""
        self.state.estimated_tokens += token_count

    def check_time_limit(self, start_time: float) -> None:
        """Check wall-clock execution time against policy timeout."""
        elapsed_sec = time.time() - start_time
        if elapsed_sec > self.policy.max_total_execution_seconds:
            raise BudgetExceededError(
                f"Execution time budget exceeded: {elapsed_sec:.1f}s "
                f"> {self.policy.max_total_execution_seconds:.1f}s"
            )

    def get_remaining_budget(self) -> dict[str, Any]:
        """Compute remaining allowances across all tracked dimensions."""
        return {
            "iterations_remaining": max(0, self.policy.max_iterations - self.state.iterations),
            "tool_calls_remaining": max(0, self.policy.max_tool_calls - self.state.tool_calls),
            "llm_calls_remaining": max(0, self.policy.max_llm_calls - self.state.llm_calls),
            "retries_remaining": max(0, self.policy.max_total_retries - self.state.retries),
            "memory_reads_remaining": max(
                0, self.policy.max_memory_retrievals - self.state.memory_reads
            ),
            "memory_writes_remaining": max(
                0, self.policy.max_memory_writes - self.state.memory_writes
            ),
            "plan_executions_remaining": max(
                0, self.policy.max_plan_executions - self.state.plan_executions
            ),
        }
