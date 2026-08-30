"""Base protocol and interface for cryptographic signing providers."""

from typing import Any, Protocol


class SigningProvider(Protocol):
    """Abstract provider interface for signing audit checkpoints."""

    def sign(self, payload: bytes) -> tuple[str, str]:
        """
        Sign the payload bytes.
        Returns tuple of (signature_hex, key_id).
        """
        ...

    def verify(self, payload: bytes, signature: str, key_id: str) -> bool:
        """
        Verify signature over payload bytes with key_id.
        Returns True if valid, False otherwise.
        """
        ...

    def get_metadata(self) -> dict[str, Any]:
        """Return signing provider metadata (algorithm, key_id, provider_type)."""
        ...
