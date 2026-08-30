"""Safe AST-based mathematical expression evaluator tool."""

import ast
import operator
from typing import Any

from app.schemas.common import RiskLevel
from app.tools.base import BaseTool
from app.tools.errors import ToolExecutionError, ToolValidationError
from app.tools.schemas import ToolDefinition, ToolPolicyClassification


class SafeMathEvaluator:
    """
    Secure deterministic AST mathematical evaluator.
    Strictly forbids Python builtins, imports, function calls, attributes, and arbitrary syntax.
    Enforces AST node, depth, operand, and exponent complexity limits.
    """

    MAX_EXPRESSION_LENGTH = 200
    MAX_NODE_COUNT = 50
    MAX_AST_DEPTH = 10
    MAX_LITERAL_MAGNITUDE = 10**9
    MAX_RESULT_MAGNITUDE = 10**15
    MAX_POWER_BASE = 1000
    MAX_POWER_EXPONENT = 50

    ALLOWED_BINARY_OPS: dict[type[ast.operator], Any] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }

    ALLOWED_UNARY_OPS: dict[type[ast.unaryop], Any] = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    @classmethod
    def evaluate(cls, expression: str) -> int | float:
        cleaned = expression.strip()
        if not cleaned:
            raise ToolValidationError("Expression cannot be empty.")

        if len(cleaned) > cls.MAX_EXPRESSION_LENGTH:
            raise ToolValidationError(
                f"Expression length ({len(cleaned)}) exceeds maximum allowed "
                f"limit of {cls.MAX_EXPRESSION_LENGTH} characters."
            )

        try:
            tree = ast.parse(cleaned, mode="eval")
        except SyntaxError as exc:
            raise ToolValidationError(
                f"Malformed mathematical expression: {str(exc)}",
                details={"expression": cleaned},
            ) from exc

        # Check total AST node count to prevent parser explosion
        nodes = list(ast.walk(tree))
        if len(nodes) > cls.MAX_NODE_COUNT:
            raise ToolValidationError(
                f"Expression complexity ({len(nodes)} AST nodes) exceeds "
                f"limit of {cls.MAX_NODE_COUNT} nodes."
            )

        return cls._eval_node(tree.body, depth=1)

    @classmethod
    def _eval_node(cls, node: ast.AST, depth: int) -> int | float:
        if depth > cls.MAX_AST_DEPTH:
            raise ToolValidationError(
                f"Expression nesting depth exceeds limit of {cls.MAX_AST_DEPTH}."
            )

        # Constant numbers (integers / floats)
        if isinstance(node, ast.Constant):
            if type(node.value) not in (int, float):
                raise ToolValidationError(
                    f"Forbidden constant type '{type(node.value).__name__}' in expression."
                )
            num_val = float(node.value) if isinstance(node.value, float) else int(node.value)
            if abs(num_val) > cls.MAX_LITERAL_MAGNITUDE:
                raise ToolValidationError(
                    f"Number literal exceeds max magnitude of {cls.MAX_LITERAL_MAGNITUDE}."
                )
            return num_val

        # Unary operations (+x, -x)
        if isinstance(node, ast.UnaryOp):
            unary_op_type = type(node.op)
            if unary_op_type not in cls.ALLOWED_UNARY_OPS:
                raise ToolValidationError(f"Forbidden unary operator: {unary_op_type.__name__}.")
            operand_val = cls._eval_node(node.operand, depth + 1)
            unary_result = cls.ALLOWED_UNARY_OPS[unary_op_type](operand_val)
            if abs(unary_result) > cls.MAX_RESULT_MAGNITUDE:
                raise ToolExecutionError(
                    f"Calculation result exceeds maximum magnitude of {cls.MAX_RESULT_MAGNITUDE}."
                )
            return float(unary_result) if isinstance(unary_result, float) else int(unary_result)

        # Binary operations (x + y, x * y, etc.)
        if isinstance(node, ast.BinOp):
            bin_op_type = type(node.op)
            if bin_op_type not in cls.ALLOWED_BINARY_OPS:
                raise ToolValidationError(f"Forbidden binary operator: {bin_op_type.__name__}.")

            left_val = cls._eval_node(node.left, depth + 1)
            right_val = cls._eval_node(node.right, depth + 1)

            # Division / modulo safeguards
            if bin_op_type in (ast.Div, ast.FloorDiv):
                if right_val == 0:
                    raise ToolExecutionError("Division by zero is undefined.")
            elif bin_op_type == ast.Mod:
                if right_val == 0:
                    raise ToolExecutionError("Modulo by zero is undefined.")
            elif bin_op_type == ast.Pow:
                if abs(left_val) > cls.MAX_POWER_BASE:
                    raise ToolExecutionError(
                        f"Base {left_val} exceeds maximum allowed base of {cls.MAX_POWER_BASE}."
                    )
                if not isinstance(right_val, int) and not (
                    isinstance(right_val, float) and right_val.is_integer()
                ):
                    raise ToolExecutionError("Exponent must be an integer.")
                int_exp = int(right_val)
                if int_exp < 0 or int_exp > cls.MAX_POWER_EXPONENT:
                    raise ToolExecutionError(
                        f"Exponent {int_exp} exceeds allowed range (0 to {cls.MAX_POWER_EXPONENT})."
                    )

            calc_func = cls.ALLOWED_BINARY_OPS[bin_op_type]
            try:
                result = calc_func(left_val, right_val)
            except OverflowError as exc:
                raise ToolExecutionError(
                    "Arithmetic overflow occurred during calculation."
                ) from exc

            if abs(result) > cls.MAX_RESULT_MAGNITUDE:
                raise ToolExecutionError(
                    f"Calculation result exceeds limit of {cls.MAX_RESULT_MAGNITUDE}."
                )

            # Normalize floating point whole numbers (e.g. 4.0 -> 4 if exact integer arithmetic)
            if isinstance(result, float) and result.is_integer():
                return int(result)
            return float(result) if isinstance(result, float) else int(result)

        # Reject any other AST node (Calls, Attributes, Names, Imports, etc.)
        raise ToolValidationError(
            f"Forbidden expression syntax: '{type(node).__name__}' is not permitted."
        )


class CalculatorTool(BaseTool):
    """
    AEGIS Built-in Calculator Tool.
    Performs deterministic arithmetic calculations securely via restricted AST evaluation.
    """

    _definition = ToolDefinition(
        name="calculator",
        description=(
            "Evaluates a mathematical expression and returns the numerical result. "
            "Supports +, -, *, /, //, %, **, parentheses, and decimals."
        ),
        version="1.0.0",
        input_schema={
            "type": "object",
            "required": ["expression"],
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate (e.g. '(25 * 4) + 10')",
                }
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "number", "description": "The computed numerical outcome"}
            },
        },
        timeout_seconds=5.0,
        enabled=True,
        policy_level=ToolPolicyClassification.SAFE,
        risk_level=RiskLevel.LOW,
        capabilities=["math", "calculation"],
        metadata={"category": "builtins"},
    )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def validate_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        super().validate_arguments(arguments)
        expression = str(arguments["expression"])
        # Validate syntax & tree structure
        cleaned = expression.strip()
        if not cleaned:
            raise ToolValidationError("Expression cannot be empty.")
        if len(cleaned) > SafeMathEvaluator.MAX_EXPRESSION_LENGTH:
            raise ToolValidationError(
                f"Expression length ({len(cleaned)}) exceeds maximum allowed "
                f"limit of {SafeMathEvaluator.MAX_EXPRESSION_LENGTH} characters."
            )
        try:
            tree = ast.parse(cleaned, mode="eval")
        except SyntaxError as exc:
            raise ToolValidationError(
                f"Malformed mathematical expression: {str(exc)}",
                details={"expression": cleaned},
            ) from exc

        nodes = list(ast.walk(tree))
        if len(nodes) > SafeMathEvaluator.MAX_NODE_COUNT:
            raise ToolValidationError(
                f"Expression complexity ({len(nodes)} AST nodes) exceeds "
                f"limit of {SafeMathEvaluator.MAX_NODE_COUNT} nodes."
            )

        # Check node types allowlist
        for n in nodes:
            if isinstance(n, ast.Expression):
                continue
            if isinstance(n, ast.BinOp | ast.UnaryOp | ast.Constant):
                continue
            if (
                type(n) in SafeMathEvaluator.ALLOWED_BINARY_OPS
                or type(n) in SafeMathEvaluator.ALLOWED_UNARY_OPS
            ):
                continue
            raise ToolValidationError(
                f"Forbidden expression syntax: '{type(n).__name__}' is not permitted."
            )

        return arguments

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        expression = str(arguments["expression"])
        result = SafeMathEvaluator.evaluate(expression)
        return {"result": result, "expression": expression}
