"""Tool Registry for discovering and registering AEGIS tools."""

from app.tools.base import BaseTool
from app.tools.builtins.calculator import CalculatorTool
from app.tools.errors import ToolNotFoundError, ToolRegistrationError
from app.tools.schemas import ToolDefinition


class ToolRegistry:
    """
    Registry for managing tool registration, lookup, and discovery.
    Decoupled from execution logic.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """
        Register a new tool instance in the registry.
        Raises ToolRegistrationError if the tool name already exists or definition is invalid.
        """
        if not isinstance(tool, BaseTool):
            raise ToolRegistrationError(
                f"Expected an instance of BaseTool, got '{type(tool).__name__}'."
            )

        name = tool.definition.name
        if not name or not isinstance(name, str):
            raise ToolRegistrationError(
                "Tool definition must contain a valid non-empty string name."
            )

        if name in self._tools:
            raise ToolRegistrationError(
                f"Tool '{name}' is already registered. Duplicate registrations are prohibited.",
                details={"tool": name},
            )

        self._tools[name] = tool

    def unregister(self, name: str) -> None:
        """
        Unregister a tool by name. Raises ToolNotFoundError if tool does not exist.
        """
        if name not in self._tools:
            raise ToolNotFoundError(f"Cannot unregister: tool '{name}' not found.")
        del self._tools[name]

    def get(self, name: str) -> BaseTool:
        """
        Retrieve a registered tool by its unique name. Raises ToolNotFoundError if missing.
        """
        if name not in self._tools:
            raise ToolNotFoundError(
                f"Tool '{name}' is not registered.",
                details={"requested_tool": name, "available_tools": list(self._tools.keys())},
            )
        return self._tools[name]

    def list_tools(self, only_enabled: bool = True) -> list[ToolDefinition]:
        """
        Return definitions of all registered tools.
        """
        definitions = [tool.definition for tool in self._tools.values()]
        if only_enabled:
            return [d for d in definitions if d.enabled]
        return definitions

    def contains(self, name: str) -> bool:
        """
        Check if a tool is present in the registry.
        """
        return name in self._tools

    def clear(self) -> None:
        """
        Remove all registered tools (useful for isolated unit tests).
        """
        self._tools.clear()


def create_default_tool_registry() -> ToolRegistry:
    """
    Factory creating a new ToolRegistry instance populated with default safe built-in tools.
    """
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    return registry
