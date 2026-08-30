"""Unit tests for ToolRegistry and tool discovery."""

import pytest
from app.schemas.common import RiskLevel
from app.tools.base import BaseTool
from app.tools.errors import ToolNotFoundError, ToolRegistrationError
from app.tools.registry import ToolRegistry, create_default_tool_registry
from app.tools.schemas import ToolDefinition, ToolPolicyClassification


class DummyCustomTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="custom_tool",
            description="Custom test tool for unit testing",
            version="1.0.0",
            input_schema={"type": "object", "properties": {"val": {"type": "string"}}},
            policy_level=ToolPolicyClassification.SAFE,
            risk_level=RiskLevel.LOW,
        )

    async def execute(self, arguments):
        return {"processed": arguments.get("val")}


def test_tool_registry_registration_and_lookup():
    registry = ToolRegistry()
    tool = DummyCustomTool()

    assert not registry.contains("custom_tool")
    registry.register(tool)
    assert registry.contains("custom_tool")

    retrieved = registry.get("custom_tool")
    assert retrieved is tool
    assert retrieved.definition.name == "custom_tool"


def test_tool_registry_duplicate_registration():
    registry = ToolRegistry()
    tool1 = DummyCustomTool()
    tool2 = DummyCustomTool()

    registry.register(tool1)
    with pytest.raises(ToolRegistrationError) as exc_info:
        registry.register(tool2)

    assert "already registered" in str(exc_info.value)


def test_tool_registry_lookup_missing():
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError) as exc_info:
        registry.get("non_existent_tool")

    assert "not registered" in str(exc_info.value)


def test_tool_registry_unregister():
    registry = ToolRegistry()
    tool = DummyCustomTool()

    registry.register(tool)
    assert registry.contains("custom_tool")

    registry.unregister("custom_tool")
    assert not registry.contains("custom_tool")

    with pytest.raises(ToolNotFoundError):
        registry.unregister("custom_tool")


def test_tool_registry_listing_and_filtering():
    registry = ToolRegistry()
    tool1 = DummyCustomTool()

    class DisabledTool(BaseTool):
        @property
        def definition(self) -> ToolDefinition:
            return ToolDefinition(
                name="disabled_tool",
                description="Disabled test tool",
                input_schema={"type": "object"},
                enabled=False,
            )

        async def execute(self, arguments):
            return {}

    registry.register(tool1)
    registry.register(DisabledTool())

    all_tools = registry.list_tools(only_enabled=False)
    assert len(all_tools) == 2

    enabled_tools = registry.list_tools(only_enabled=True)
    assert len(enabled_tools) == 1
    assert enabled_tools[0].name == "custom_tool"


def test_tool_registry_isolation():
    reg1 = create_default_tool_registry()
    reg2 = create_default_tool_registry()

    assert reg1.contains("calculator")
    assert reg2.contains("calculator")

    reg1.register(DummyCustomTool())
    assert reg1.contains("custom_tool")
    assert not reg2.contains("custom_tool")  # Fully isolated instance


def test_tool_registry_invalid_registration():
    registry = ToolRegistry()
    with pytest.raises(ToolRegistrationError):
        registry.register("not_a_tool")  # type: ignore
