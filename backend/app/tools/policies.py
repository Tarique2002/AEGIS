"""Security policy enforcement for tool invocations."""

import json

from app.tools.errors import ToolPolicyViolationError
from app.tools.schemas import ToolDefinition, ToolInvocation, ToolPolicyClassification

# Maximum allowed serialized arguments payload size (64 KB)
MAX_ARGUMENT_PAYLOAD_BYTES = 64 * 1024


class ToolPolicy:
    """
    Security gate that validates whether a tool invocation is permissible
    under current platform risk policies and operational constraints.
    """

    def __init__(
        self,
        allowed_classifications: set[ToolPolicyClassification] | None = None,
        max_payload_bytes: int = MAX_ARGUMENT_PAYLOAD_BYTES,
    ) -> None:
        # Phase 2 strictly permits only SAFE classification
        self.allowed_classifications = allowed_classifications or {
            ToolPolicyClassification.SAFE,
        }
        self.max_payload_bytes = max_payload_bytes

    def validate_invocation(
        self,
        tool_definition: ToolDefinition,
        invocation: ToolInvocation,
    ) -> None:
        """
        Validate that the target tool is enabled, policy classification is allowed,
        and payload constraints are met.
        Raises ToolPolicyViolationError on violation.
        """
        # 1. Check enabled state
        if not tool_definition.enabled:
            raise ToolPolicyViolationError(
                f"Tool '{tool_definition.name}' is currently disabled.",
                details={"tool": tool_definition.name, "reason": "tool_disabled"},
            )

        # 2. Check classification policy tier
        if tool_definition.policy_level not in self.allowed_classifications:
            raise ToolPolicyViolationError(
                f"Execution of '{tool_definition.policy_level.value}' tool "
                f"'{tool_definition.name}' is prohibited by current security policy.",
                details={
                    "tool": tool_definition.name,
                    "policy_level": tool_definition.policy_level.value,
                    "allowed_levels": [c.value for c in self.allowed_classifications],
                },
            )

        # 3. Check payload size constraints
        try:
            serialized_size = len(json.dumps(invocation.arguments).encode("utf-8"))
            if serialized_size > self.max_payload_bytes:
                raise ToolPolicyViolationError(
                    f"Tool argument payload size ({serialized_size} bytes) exceeds "
                    f"maximum limit of {self.max_payload_bytes} bytes.",
                    details={"size_bytes": serialized_size, "limit_bytes": self.max_payload_bytes},
                )
        except (TypeError, ValueError) as exc:
            raise ToolPolicyViolationError(
                f"Unserializable tool arguments: {str(exc)}",
                details={"tool": tool_definition.name},
            ) from exc
