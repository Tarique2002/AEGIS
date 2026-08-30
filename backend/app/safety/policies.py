"""Platform safety policies and configuration rules for the AEGIS risk boundary."""

import ipaddress
import urllib.parse

from pydantic import Field

from app.core.config import settings
from app.safety.errors import SafetyPolicyViolationError
from app.safety.schemas import RiskCategory, RiskLevel
from app.schemas.common import AegisBaseSchema


class SafetyPolicy(AegisBaseSchema):
    """
    Authoritative safety policy declaring risk tolerances, approval requirements,
    payload bounds, SSRF rules, and path safety constraints.
    """

    policy_version: str = "1.0.0"
    max_risk_level: RiskLevel = RiskLevel.CRITICAL
    allowed_categories: list[RiskCategory] = Field(
        default_factory=lambda: [
            RiskCategory.READ_ONLY,
            RiskCategory.COMPUTATION,
            RiskCategory.DATA_ACCESS,
            RiskCategory.MEMORY_WRITE,
            RiskCategory.AUTHENTICATION,
            RiskCategory.PRIVACY,
            RiskCategory.SECURITY,
        ]
    )
    denied_categories: list[RiskCategory] = Field(
        default_factory=lambda: [
            RiskCategory.DESTRUCTIVE,
            RiskCategory.CODE_EXECUTION,
            RiskCategory.SYSTEM_OPERATION,
        ]
    )
    require_approval_above: RiskLevel = RiskLevel.MEDIUM
    max_action_duration_seconds: float = 300.0
    max_payload_size_bytes: int = 1_048_576  # 1 MB
    max_external_calls: int = 10
    max_concurrent_actions: int = 5
    approval_ttl_seconds: int = 300
    environment: str = "development"

    # SSRF Blacklist Patterns
    disallowed_schemes: list[str] = Field(
        default_factory=lambda: ["file", "gopher", "data", "ftp", "ldap", "dict"]
    )
    blocked_hosts: list[str] = Field(
        default_factory=lambda: [
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "169.254.169.254",  # AWS/GCP/Azure instance metadata
            "metadata.google.internal",
        ]
    )

    # Path Safety Blacklist Patterns
    sensitive_path_prefixes: list[str] = Field(
        default_factory=lambda: [
            "/etc",
            "/root",
            "/sys",
            "/proc",
            "/dev",
            "C:\\Windows",
            "C:\\Program Files",
            "C:\\ProgramData",
        ]
    )

    def validate_action_risk(
        self,
        risk_level: RiskLevel,
        categories: list[RiskCategory],
    ) -> None:
        """Verify that action risk level and categories conform to policy."""
        # 1. Denied categories check
        for cat in categories:
            if cat in self.denied_categories:
                raise SafetyPolicyViolationError(
                    f"Action categorized as '{cat.value}' is explicitly DENIED by platform "
                    "safety policy."
                )

        # 2. Risk level ceiling check
        risk_order = [
            RiskLevel.NONE,
            RiskLevel.LOW,
            RiskLevel.MEDIUM,
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        ]
        action_idx = (
            risk_order.index(risk_level) if risk_level in risk_order else len(risk_order) - 1
        )
        max_idx = (
            risk_order.index(self.max_risk_level)
            if self.max_risk_level in risk_order
            else len(risk_order) - 1
        )

        if action_idx > max_idx:
            raise SafetyPolicyViolationError(
                f"Action risk level '{risk_level.value}' exceeds maximum permitted "
                f"'{self.max_risk_level.value}'."
            )

    def validate_url_safety(self, url: str) -> None:
        """Validate that a URL does not target loopback, private networks, or metadata services."""
        if not url:
            return

        try:
            parsed = urllib.parse.urlparse(url)
        except Exception as exc:
            raise SafetyPolicyViolationError(f"Malformed URL: {exc}") from exc

        scheme = (parsed.scheme or "").lower()
        if scheme in self.disallowed_schemes:
            raise SafetyPolicyViolationError(
                f"Disallowed URL scheme '{scheme}'. Only HTTP/HTTPS is permitted."
            )

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return

        if hostname in self.blocked_hosts:
            raise SafetyPolicyViolationError(
                f"URL target '{hostname}' is blocked by SSRF safety defense."
            )

        # Check IP address targets
        try:
            ip = ipaddress.ip_address(hostname)
            if (
                ip.is_loopback
                or ip.is_private
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise SafetyPolicyViolationError(
                    f"Access to private/local IP address '{hostname}' is forbidden."
                )
        except ValueError:
            # Hostname is not an IP literal
            pass

    def validate_path_safety(self, path: str) -> None:
        """Ensure filesystem path prevents directory traversal and sensitive directory escape."""
        if not path:
            return

        # Check for directory traversal sequences
        if ".." in path:
            raise SafetyPolicyViolationError(
                "Directory traversal sequence '..' detected in path argument."
            )

        norm_path = path.replace("\\", "/").lower()
        for prefix in self.sensitive_path_prefixes:
            norm_prefix = prefix.replace("\\", "/").lower()
            if norm_path.startswith(norm_prefix):
                raise SafetyPolicyViolationError(
                    f"Access to sensitive system path '{path}' is blocked by policy."
                )


def get_default_safety_policy() -> SafetyPolicy:
    """Instantiate default environment-aware safety policy."""
    is_prod = settings.ENVIRONMENT.value == "production"
    return SafetyPolicy(
        environment=settings.ENVIRONMENT.value,
        max_risk_level=RiskLevel.HIGH if is_prod else RiskLevel.CRITICAL,
        require_approval_above=RiskLevel.LOW if is_prod else RiskLevel.MEDIUM,
        approval_ttl_seconds=settings.APPROVAL_TTL_SECONDS,
        max_payload_size_bytes=settings.REQUEST_MAX_BYTES,
    )
