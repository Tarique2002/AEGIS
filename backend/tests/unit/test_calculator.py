"""Unit and security tests for the Safe AST CalculatorTool."""

import pytest
from app.tools.builtins.calculator import CalculatorTool, SafeMathEvaluator
from app.tools.errors import ToolExecutionError, ToolValidationError


@pytest.mark.asyncio
async def test_calculator_basic_arithmetic():
    calc = CalculatorTool()

    # Addition
    res = await calc.execute({"expression": "2 + 2"})
    assert res["result"] == 4

    # Subtraction
    res = await calc.execute({"expression": "100 - 35"})
    assert res["result"] == 65

    # Multiplication
    res = await calc.execute({"expression": "10 * 5"})
    assert res["result"] == 50

    # Division
    res = await calc.execute({"expression": "100 / 4"})
    assert res["result"] == 25

    # Floor Division
    res = await calc.execute({"expression": "17 // 5"})
    assert res["result"] == 3

    # Modulo
    res = await calc.execute({"expression": "17 % 5"})
    assert res["result"] == 2

    # Exponentiation
    res = await calc.execute({"expression": "2 ** 8"})
    assert res["result"] == 256


@pytest.mark.asyncio
async def test_calculator_complex_expressions():
    calc = CalculatorTool()

    # Nested parentheses
    res = await calc.execute({"expression": "(10 + 5) * 3"})
    assert res["result"] == 45

    # Decimals
    res = await calc.execute({"expression": "3.5 * 2 + 1.25"})
    assert res["result"] == 8.25

    # Unary operators
    res = await calc.execute({"expression": "-5 + +10"})
    assert res["result"] == 5

    # Multi-operator precedence
    res = await calc.execute({"expression": "(25 * 4) + 10"})
    assert res["result"] == 110


def test_calculator_division_and_modulo_by_zero():
    with pytest.raises(ToolExecutionError) as exc_info:
        SafeMathEvaluator.evaluate("10 / 0")
    assert "Division by zero" in str(exc_info.value)

    with pytest.raises(ToolExecutionError) as exc_info:
        SafeMathEvaluator.evaluate("10 // 0")
    assert "Division by zero" in str(exc_info.value)

    with pytest.raises(ToolExecutionError) as exc_info:
        SafeMathEvaluator.evaluate("10 % 0")
    assert "Modulo by zero" in str(exc_info.value)


def test_calculator_empty_and_length_limits():
    with pytest.raises(ToolValidationError):
        SafeMathEvaluator.evaluate("")

    with pytest.raises(ToolValidationError):
        SafeMathEvaluator.evaluate("   ")

    long_expr = "1 + " * 100 + "1"
    with pytest.raises(ToolValidationError) as exc_info:
        SafeMathEvaluator.evaluate(long_expr)
    assert "exceeds maximum allowed limit" in str(exc_info.value)


def test_calculator_exponent_safeguards():
    # Base too large
    with pytest.raises(ToolExecutionError) as exc_info:
        SafeMathEvaluator.evaluate("1001 ** 2")
    assert "exceeds maximum allowed base" in str(exc_info.value)

    # Exponent too large
    with pytest.raises(ToolExecutionError) as exc_info:
        SafeMathEvaluator.evaluate("2 ** 51")
    assert "exceeds allowed range" in str(exc_info.value)

    # Negative exponent rejected
    with pytest.raises(ToolExecutionError) as exc_info:
        SafeMathEvaluator.evaluate("2 ** -3")
    assert "exceeds allowed range" in str(exc_info.value)


def test_calculator_number_magnitude_limit():
    with pytest.raises(ToolValidationError) as exc_info:
        SafeMathEvaluator.evaluate("1000000001 + 1")
    assert "exceeds max magnitude" in str(exc_info.value)


@pytest.mark.parametrize(
    "malicious_code",
    [
        "__import__('os').system('ls')",
        "eval('1 + 1')",
        "exec('x = 1')",
        "open('/etc/passwd')",
        "print('hello')",
        "os.environ",
        "math.sin(1)",
        "x + 5",
        "lambda x: x * 2",
        "[x for x in (1, 2, 3)]",
        '{"key": 1}',
        "[1, 2, 3]",
        "(1, 2, 3)",
        "'string' + 'concat'",
        "True + False",
        "None",
        "int('5')",
    ],
)
def test_calculator_security_rejection(malicious_code: str):
    """
    Verify that ANY non-arithmetic syntax, attribute access, function call,
    name lookup, import, comprehension, or variable access is strictly rejected.
    """
    with pytest.raises(ToolValidationError):
        SafeMathEvaluator.evaluate(malicious_code)
