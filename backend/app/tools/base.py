"""Base class and interface definition for AEGIS tools."""

from abc import ABC, abstractmethod
from typing import Any

from app.tools.errors import ToolValidationError
from app.tools.schemas import ToolDefinition


class BaseTool(ABC):
    """
    Abstract interface that all AEGIS tools must implement.
    Decouples tool definition and validation from execution.
    """

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Return the immutable definition and schema of the tool."""
        ...

    def validate_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Validate input arguments against the tool's declared input_schema.
        Subclasses may override with model-specific Pydantic validation.
        """
        schema = self.definition.input_schema
        required_fields = schema.get("required", [])
        properties = schema.get("properties", {})

        # Check required fields
        for field_name in required_fields:
            if field_name not in arguments:
                raise ToolValidationError(
                    f"Missing required parameter '{field_name}' for tool '{self.definition.name}'.",
                    details={"tool": self.definition.name, "missing_parameter": field_name},
                )

        # Check basic types if specified in properties
        type_mapping: dict[str, type | tuple[type, ...]] = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        for param_name, param_value in arguments.items():
            if param_name in properties:
                expected_type_name = properties[param_name].get("type")
                if expected_type_name in type_mapping:
                    expected_python_type = type_mapping[expected_type_name]
                    is_num = expected_type_name in ("integer", "number")
                    if is_num and isinstance(param_value, bool):
                        raise ToolValidationError(
                            f"Invalid type for '{param_name}'. "
                            f"Expected {expected_type_name}, got boolean.",
                            details={"parameter": param_name, "expected": expected_type_name},
                        )

                    if not isinstance(param_value, expected_python_type):
                        raise ToolValidationError(
                            f"Invalid type for '{param_name}'. Expected {expected_type_name}, "
                            f"got {type(param_value).__name__}.",
                            details={"parameter": param_name, "expected": expected_type_name},
                        )

        return arguments

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> Any:
        """
        Execute tool functionality with validated input arguments.
        Must be asynchronous and safe.
        """
        ...
