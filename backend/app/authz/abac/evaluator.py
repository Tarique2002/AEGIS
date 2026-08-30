"""Evaluator for ABAC rules and CEL policy expressions."""

from typing import Any

from app.authz.abac.cache import CompiledPolicyCache
from app.authz.abac.context import AuthorizationContext
from app.authz.abac.policies import ABACPolicyRule
from app.authz.cel.compiler import CELCompiler
from app.authz.cel.evaluator import CELEvaluator
from app.core.logging import get_logger

logger = get_logger("aegis.authz.abac.evaluator")


class ABACEvaluator:
    """Evaluates ABAC policy rules and CEL expressions against AuthorizationContext."""

    def __init__(
        self,
        compiler: CELCompiler | None = None,
        evaluator: CELEvaluator | None = None,
        cache: CompiledPolicyCache | None = None,
    ) -> None:
        self.compiler = compiler or CELCompiler()
        self.evaluator = evaluator or CELEvaluator()
        self.cache = cache or CompiledPolicyCache()

    def evaluate_rule(
        self,
        rule: ABACPolicyRule,
        context: AuthorizationContext,
    ) -> bool:
        """
        Evaluate an ABAC rule against the provided AuthorizationContext.
        Returns True if rule conditions/expression match the context, False otherwise.
        """
        if not rule.enabled:
            return False

        eval_dict = context.to_eval_dict()

        # 1. Evaluate dictionary conditions if specified
        if rule.conditions:
            for key, val in rule.conditions.items():
                # Support nested dot notation e.g. "resource.sensitivity"
                parts = key.split(".")
                curr: Any = eval_dict
                for part in parts:
                    if isinstance(curr, dict) and part in curr:
                        curr = curr[part]
                    else:
                        curr = None
                        break
                if curr != val:
                    return False

        # 2. Evaluate CEL expression if specified
        if rule.cel_expression:
            ast = self.cache.get(rule.tenant_id, rule.policy_id, rule.version)
            if ast is None:
                comp_res = self.compiler.compile(rule.cel_expression, rule.policy_id, rule.version)
                if not comp_res.valid:
                    logger.warning(
                        f"Policy {rule.policy_id} failed CEL compilation during evaluation: "
                        f"{comp_res.errors}"
                    )
                    return False
                ast = comp_res.ast
                self.cache.set(rule.tenant_id, rule.policy_id, rule.version, ast)

            match = self.evaluator.evaluate(ast, eval_dict)
            if not match:
                return False

        return True
