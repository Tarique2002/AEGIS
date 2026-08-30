"""CEL Evaluator executing compiled AST against typed evaluation context."""

from typing import Any

import celpy

from app.authz.cel.environment import get_cel_environment
from app.authz.cel.errors import CELEvaluationError
from app.core.logging import get_logger

logger = get_logger("aegis.authz.cel.evaluator")


class CELEvaluator:
    """Evaluates compiled CEL programs in a restricted environment."""

    def __init__(self, env: celpy.Environment | None = None) -> None:
        self.env = env or get_cel_environment()

    def evaluate(self, ast: Any, context_dict: dict[str, Any]) -> bool:
        """
        Evaluate a compiled CEL AST with variables provided in context_dict.
        Returns boolean verdict.
        """
        try:
            program = self.env.program(ast)
            cel_context: Any = celpy.json_to_cel(context_dict)
            raw_result = program.evaluate(cel_context)

            # Celpy boolean extraction
            if isinstance(raw_result, celpy.celtypes.BoolType):
                return bool(raw_result)
            return bool(raw_result)
        except Exception as exc:
            logger.info(f"CEL Evaluation error: {exc}")
            return False

    def evaluate_or_raise(self, ast: Any, context_dict: dict[str, Any]) -> bool:
        """Evaluate CEL AST, raising CELEvaluationError on evaluation errors."""
        try:
            program = self.env.program(ast)
            cel_context: Any = celpy.json_to_cel(context_dict)
            raw_result = program.evaluate(cel_context)
            return bool(raw_result)
        except Exception as exc:
            logger.warning(f"CEL evaluation failed with exception: {exc}")
            raise CELEvaluationError(
                f"CEL Evaluation error: {exc}",
                details={"error": str(exc)},
            ) from exc
