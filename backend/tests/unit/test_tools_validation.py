"""Unit tests for tool parameter validation and schema verification."""

import pytest
from app.tools.builtins.calculator import CalculatorTool
from app.tools.errors import ToolValidationError


def test_calculator_validation_success():
    calc = CalculatorTool()
    validated = calc.validate_arguments({"expression": "10 * 20"})
    assert validated == {"expression": "10 * 20"}


def test_calculator_validation_missing_required_argument():
    calc = CalculatorTool()
    with pytest.raises(ToolValidationError) as exc_info:
        calc.validate_arguments({})

    assert "Missing required parameter 'expression'" in str(exc_info.value)


def test_calculator_validation_wrong_type():
    calc = CalculatorTool()
    with pytest.raises(ToolValidationError) as exc_info:
        calc.validate_arguments({"expression": 12345})  # should be string

    assert "Invalid type for 'expression'" in str(exc_info.value)


def test_tool_validation_boolean_type_check():
    calc = CalculatorTool()
    with pytest.raises(ToolValidationError) as exc_info:
        calc.validate_arguments({"expression": True})  # bool is not string

    assert "Invalid type for 'expression'" in str(exc_info.value)
