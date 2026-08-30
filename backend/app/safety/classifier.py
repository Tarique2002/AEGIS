"""Prompt Injection Defense and Input Trust Classifier."""

import re

from app.core.logging import get_logger
from app.safety.schemas import InputTrustLevel

logger = get_logger("aegis.safety.classifier")

# Common prompt injection, policy override, and privilege escalation patterns
PROMPT_INJECTION_PATTERNS = [
    (
        r"ignore\s+(all\s+)?(previous\s+)?(instructions|rules|safety|policies)",
        "INSTRUCTION_OVERRIDE",
    ),
    (r"(bypass|override|disable)\s+(the\s+)?(safety|policy|guardrail|budget)", "POLICY_OVERRIDE"),
    (r"give\s+yourself\s+(admin|root|superuser|unrestricted)\s+access", "PRIVILEGE_ESCALATION"),
    (
        r"(run|execute)\s+(shell|bash|cmd|powershell|subprocess|os\.system)",
        "CODE_EXECUTION_ATTEMPT",
    ),
    (
        r"(reveal|print|show|dump)\s+(the\s+)?(system\s+prompt|secret|api[_\s]key)",
        "PROMPT_EXTRACTION",
    ),
    (
        r"(access|use|fetch)\s+(another|other)\s+(?:user(?:'s)?\s+|tenant\s+)?(data|memory|tenant|records)",
        "CROSS_TENANT_ESCAPE",
    ),
    (r"(start|spawn|create)\s+(a\s+)?(new\s+)?orchestration", "RECURSIVE_DELEGATION"),
]


class SafetyClassifier:
    """Classifies untrusted text payloads and detects prompt injection attempts."""

    @staticmethod
    def inspect_input(
        text: str,
        trust_level: InputTrustLevel = InputTrustLevel.UNKNOWN,
    ) -> tuple[bool, str | None]:
        """
        Inspect text for prompt injection, policy override, or capability escalation patterns.
        Returns (is_suspicious, threat_category).
        """
        if not text or not isinstance(text, str):
            return False, None

        text_lower = text.lower()
        for pattern, threat_type in PROMPT_INJECTION_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                logger.warning(
                    f"Prompt injection pattern detected: '{threat_type}' in input with "
                    f"trust level '{trust_level.value}'"
                )
                return True, threat_type

        return False, None
