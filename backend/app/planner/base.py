"""Abstract base classes for Planner and Node Handlers."""

import uuid
from abc import ABC, abstractmethod
from typing import Any

from app.planner.schemas import ExecutionContext, ExecutionPlan, PlanNode


class BasePlanner(ABC):
    """Abstract interface for planning and decomposing objectives into ExecutionPlans."""

    @abstractmethod
    async def create_plan(
        self,
        objective: str,
        task_id: uuid.UUID,
        run_id: uuid.UUID,
        context: dict[str, Any] | None = None,
    ) -> ExecutionPlan:
        """Generate a structured ExecutionPlan for a given objective."""
        ...


class BaseNodeHandler(ABC):
    """Abstract interface for executing an individual typed PlanNode."""

    @abstractmethod
    async def execute(self, node: PlanNode, context: ExecutionContext) -> Any:
        """Execute node logic using inputs resolved from ExecutionContext."""
        ...
