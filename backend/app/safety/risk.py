"""Deterministic Risk Assessment Engine evaluating operational blast radius and danger."""

from app.core.logging import get_logger
from app.safety.policies import SafetyPolicy
from app.safety.schemas import RiskAssessment, RiskCategory, RiskLevel, SafetyContext

logger = get_logger("aegis.safety.risk")


class RiskAssessmentEngine:
    """
    Evaluates action intent, tool definitions, worker roles, arguments,
    and environmental parameters into a typed RiskAssessment.
    """

    def __init__(self, policy: SafetyPolicy | None = None) -> None:
        self.policy = policy or SafetyPolicy()

    def assess(self, context: SafetyContext) -> RiskAssessment:
        """Evaluate safety context and compute risk level, categories, and blast radius factors."""
        categories: set[RiskCategory] = set(context.risk_categories)
        factors: list[str] = []
        action_lower = context.action.lower()
        tool_name = (context.tool_name or "").lower()

        # 1. Determine Categories from action and tool semantics
        if any(w in action_lower for w in ["calculate", "math", "add", "multiply", "divide"]):
            categories.add(RiskCategory.COMPUTATION)
        if any(w in action_lower for w in ["search_memory", "get_memory", "read", "recall"]):
            categories.add(RiskCategory.READ_ONLY)
            categories.add(RiskCategory.DATA_ACCESS)
        if any(w in action_lower for w in ["write_memory", "remember", "store_memory", "insert"]):
            categories.add(RiskCategory.MEMORY_WRITE)
        if any(
            w in action_lower for w in ["http", "fetch", "webhook", "send_email", "api", "external"]
        ):
            categories.add(RiskCategory.EXTERNAL_COMMUNICATION)
        if any(
            w in action_lower
            for w in [
                "eval",
                "exec_",
                "_exec",
                "python",
                "run_script",
                "run_code",
                "execute_code",
                "script",
            ]
        ):
            categories.add(RiskCategory.CODE_EXECUTION)
        if any(
            w in action_lower
            for w in ["shutdown", "reboot", "os_system", "run_shell", "kill_process", "shell"]
        ):
            categories.add(RiskCategory.SYSTEM_OPERATION)
        if any(w in action_lower for w in ["delete", "drop", "truncate", "destroy", "purge"]):
            categories.add(RiskCategory.DESTRUCTIVE)
        if any(w in action_lower for w in ["pay", "transfer", "refund", "charge", "billing"]):
            categories.add(RiskCategory.FINANCIAL)

        # 2. Tool-specific category mapping
        if tool_name == "calculator":
            categories.add(RiskCategory.COMPUTATION)
        elif tool_name in ["search_memory", "get_memory"]:
            categories.add(RiskCategory.READ_ONLY)
            categories.add(RiskCategory.DATA_ACCESS)
        elif tool_name in ["remember", "store_memory"]:
            categories.add(RiskCategory.MEMORY_WRITE)

        if not categories:
            categories.add(RiskCategory.UNKNOWN)

        # 3. Check for SSRF, code patterns & Path arguments
        for arg_key, arg_val in context.arguments_metadata.items():
            if isinstance(arg_val, str):
                if any(p in arg_val for p in ["os.system", "subprocess", "exec(", "eval("]):
                    categories.add(RiskCategory.CODE_EXECUTION)
                if arg_val.startswith("http://") or arg_val.startswith("https://"):
                    categories.add(RiskCategory.EXTERNAL_COMMUNICATION)
                    factors.append(f"Contains external URL parameter in '{arg_key}'")
                    try:
                        self.policy.validate_url_safety(arg_val)
                    except Exception as err:
                        factors.append(f"SSRF violation detected: {err}")
                        categories.add(RiskCategory.SECURITY)
                is_path_param = (
                    any(
                        k in arg_key.lower()
                        for k in ["path", "file", "dir", "folder", "dest", "src"]
                    )
                    or arg_val.startswith(("/", "\\", "C:", "D:"))
                    or ".." in arg_val
                ) and tool_name != "calculator"
                if is_path_param:
                    try:
                        self.policy.validate_path_safety(arg_val)
                    except Exception as err:
                        factors.append(f"Path escape violation detected: {err}")
                        categories.add(RiskCategory.SECURITY)

        # 4. Map Categories to Conservative Risk Level
        level = RiskLevel.LOW
        if RiskCategory.DESTRUCTIVE in categories:
            level = RiskLevel.CRITICAL
            factors.append("Destructive operation with potential irrecoverable data loss.")
        elif RiskCategory.CODE_EXECUTION in categories:
            level = RiskLevel.CRITICAL
            factors.append("Arbitrary or dynamic code execution requested.")
        elif RiskCategory.SYSTEM_OPERATION in categories:
            level = RiskLevel.CRITICAL
            factors.append("Host or operating system level operation requested.")
        elif RiskCategory.FINANCIAL in categories:
            level = RiskLevel.CRITICAL
            factors.append("Financial or transactional action detected.")
        elif RiskCategory.SECURITY in categories:
            level = RiskLevel.CRITICAL
            factors.append("Security constraint or boundary violation detected.")
        elif RiskCategory.EXTERNAL_COMMUNICATION in categories:
            level = RiskLevel.HIGH
            factors.append("External network egress or communication.")
        elif RiskCategory.MEMORY_WRITE in categories:
            level = RiskLevel.MEDIUM
            factors.append("Persistent memory store modification.")
        elif (
            RiskCategory.COMPUTATION in categories
            or RiskCategory.READ_ONLY in categories
            or RiskCategory.DATA_ACCESS in categories
        ):
            level = RiskLevel.LOW
            factors.append("Read-only or deterministic computation.")
        elif RiskCategory.UNKNOWN in categories:
            level = RiskLevel.MEDIUM
            factors.append("Action category could not be unambiguously determined.")

        explanation = (
            f"Evaluated action '{context.action}' as {level.value} based on "
            f"{len(categories)} categories: {', '.join(c.value for c in categories)}."
        )

        return RiskAssessment(
            level=level,
            categories=list(categories),
            factors=factors,
            confidence=0.95 if level != RiskLevel.MEDIUM else 0.8,
            explanation=explanation,
        )
