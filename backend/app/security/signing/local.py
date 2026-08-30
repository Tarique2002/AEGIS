"""Local cryptographic signing provider using HMAC-SHA256."""

import hashlib
import hmac
import os
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("aegis.security.signing.local")


class LocalSigningProvider:
    """Production-grade local signing provider using HMAC-SHA256."""

    def __init__(
        self,
        signing_key: bytes | None = None,
        key_id: str | None = None,
    ) -> None:
        # Load from settings / env or generate cryptographically secure local key
        configured_secret = getattr(settings, "AUDIT_SIGNING_KEY", None) or os.environ.get(
            "AUDIT_SIGNING_KEY"
        )
        if signing_key:
            self._key = signing_key
        elif configured_secret:
            self._key = configured_secret.encode("utf-8")
        else:
            # Generate deterministic fallback for dev / offline test execution
            self._key = hashlib.sha256(
                (settings.SECRET_KEY + ":audit-signing-key").encode("utf-8")
            ).digest()

        self.key_id = key_id or f"local-key-{hashlib.sha256(self._key).hexdigest()[:8]}"
        self.algorithm = "HMAC-SHA256"
        self.provider_type = "LOCAL"

    def sign(self, payload: bytes) -> tuple[str, str]:
        """Sign payload bytes with HMAC-SHA256, returning (hex_signature, key_id)."""
        sig = hmac.new(self._key, payload, hashlib.sha256).hexdigest()
        return sig, self.key_id

    def verify(self, payload: bytes, signature: str, key_id: str) -> bool:
        """Verify HMAC-SHA256 signature using constant-time digest comparison."""
        if key_id != self.key_id:
            logger.warning(f"Key ID mismatch: expected '{self.key_id}', got '{key_id}'")
            return False
        expected_sig = hmac.new(self._key, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, signature)

    def get_metadata(self) -> dict[str, Any]:
        """Return provider metadata."""
        return {
            "provider_type": self.provider_type,
            "algorithm": self.algorithm,
            "key_id": self.key_id,
        }
