"""CEL Compiler for parsing, validating, and type-checking authorization policies."""

import re
import uuid
from typing import Any

import celpy
from pydantic import BaseModel, Field

from app.authz.cel.environment import get_cel_environment
from app.authz.cel.errors import CELCompilationError
from app.core.logging import get_logger

logger = get_logger("aegis.authz.cel.compiler")

FORBIDDEN_PATTERNS = [
    r"__\w+__",  # python dunders
    r"\bimport\b",
    r"\beval\b",
    r"\bexec\b",
    r"\bopen\b",
    r"\bos\.",
    r"\bsubprocess\b",
    r"\bsys\.",
]


class PolicyCompilationResult(BaseModel):
    """Result of compiling and validating a CEL policy expression."""

    valid: bool
    policy_id: uuid.UUID | None = None
    version: str = "1.0.0"
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    ast: Any = None


class CELCompiler:
    """Production CEL policy compiler enforcing security restrictions and AST validation."""

    def __init__(self, env: celpy.Environment | None = None) -> None:
        self.env = env or get_cel_environment()

    def compile(
        self,
        expression: str,
        policy_id: uuid.UUID | None = None,
        version: str = "1.0.0",
    ) -> PolicyCompilationResult:
        """Parse, validate, and compile a CEL expression into an executable AST."""
        if not expression or not expression.strip():
            return PolicyCompilationResult(
                valid=False,
                policy_id=policy_id,
                version=version,
                errors=["CEL expression cannot be empty."],
            )

        expr_clean = expression.strip()

        # 1. Security pattern scan
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, expr_clean, re.IGNORECASE):
                logger.warning(
                    f"Security violation during CEL compilation: forbidden pattern '{pattern}'"
                )
                return PolicyCompilationResult(
                    valid=False,
                    policy_id=policy_id,
                    version=version,
                    errors=[f"Expression contains disallowed pattern '{pattern}'."],
                )

        # 2. Syntax parsing and compilation via celpy
        try:
            ast = self.env.compile(expr_clean)
            return PolicyCompilationResult(
                valid=True,
                policy_id=policy_id,
                version=version,
                ast=ast,
            )
        except Exception as exc:
            logger.info(f"CEL compilation error for expression '{expr_clean}': {exc}")
            return PolicyCompilationResult(
                valid=False,
                policy_id=policy_id,
                version=version,
                errors=[str(exc)],
            )

    def validate_or_raise(
        self,
        expression: str,
        policy_id: uuid.UUID | None = None,
        version: str = "1.0.0",
    ) -> PolicyCompilationResult:
        """Compile expression and raise CELCompilationError if invalid."""
        res = self.compile(expression, policy_id, version)
        if not res.valid:
            raise CELCompilationError(
                f"CEL Policy compilation failed: {'; '.join(res.errors)}",
                details={"errors": res.errors, "expression": expression},
            )
        return res
