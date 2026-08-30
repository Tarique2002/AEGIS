"""Tool Service layer providing application boundary and dependency isolation."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.executor import ToolExecutor
from app.tools.policies import ToolPolicy
from app.tools.registry import ToolRegistry, create_default_tool_registry
from app.tools.schemas import ToolDefinition, ToolInvocation, ToolObservation


class ToolService:
    """
    Service boundary for tool discovery and execution.
    Enforces that all tool execution requests pass strictly through
    Registry -> Validation -> Policy -> Executor -> Observation pipeline.
    """

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        policy: ToolPolicy | None = None,
        executor: ToolExecutor | None = None,
    ) -> None:
        self.registry = registry or create_default_tool_registry()
        self.policy = policy or ToolPolicy()
        self.executor = executor or ToolExecutor(
            registry=self.registry,
            policy=self.policy,
        )

    def list_tools(self, only_enabled: bool = True) -> list[ToolDefinition]:
        """Return definitions of all registered tools."""
        return self.registry.list_tools(only_enabled=only_enabled)

    def get_tool_by_name(self, name: str) -> ToolDefinition:
        """Retrieve the declaration and schema for a specific tool."""
        tool = self.registry.get(name)
        return tool.definition

    async def execute_tool(
        self,
        invocation: ToolInvocation,
        session: AsyncSession | None = None,
    ) -> ToolObservation:
        """
        Execute a tool through the secure executor pipeline.
        Never calls tool functions directly.
        """
        return await self.executor.execute(invocation, session=session)
