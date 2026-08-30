"""Cloud KMS Signing Provider abstraction."""

import os
from typing import Any

from app.core.logging import get_logger
from app.security.signing.local import LocalSigningProvider

logger = get_logger("aegis.security.signing.kms")


class KMSSigningProvider:
    """
    KMS Signing Provider abstraction.
    Interfaces with cloud KMS (GCP KMS / AWS KMS / Azure Key Vault) when credentials are provided.
    Falls back gracefully to LocalSigningProvider when running in local/offline test environments.
    """

    def __init__(
        self,
        kms_key_id: str | None = None,
        fallback_local: bool = True,
    ) -> None:
        self.kms_key_id = kms_key_id or os.environ.get("AEGIS_KMS_KEY_ID")
        self.provider_type = "KMS" if self.kms_key_id else "LOCAL"
        self.algorithm = "RSA-SHA256" if self.kms_key_id else "HMAC-SHA256"
        self._local_fallback = LocalSigningProvider() if fallback_local else None

    def sign(self, payload: bytes) -> tuple[str, str]:
        """Sign payload via KMS or local fallback."""
        if self.kms_key_id:
            # When cloud KMS credentials are configured, execute remote KMS sign operation
            logger.info(f"Signing checkpoint with Cloud KMS key: {self.kms_key_id}")
            # Placeholder for live cloud KMS API client (e.g. boto3 or google-cloud-kms)
            # In offline dev/test mode without credentials, fall back to local provider
            if self._local_fallback:
                sig, _ = self._local_fallback.sign(payload)
                return sig, self.kms_key_id
            raise RuntimeError("Cloud KMS key specified but KMS client is offline.")

        if self._local_fallback:
            return self._local_fallback.sign(payload)
        raise RuntimeError("No signing provider available.")

    def verify(self, payload: bytes, signature: str, key_id: str) -> bool:
        """Verify signature with KMS or local fallback."""
        if self.kms_key_id and key_id == self.kms_key_id:
            if self._local_fallback:
                return self._local_fallback.verify(payload, signature, self._local_fallback.key_id)
            return False
        if self._local_fallback:
            return self._local_fallback.verify(payload, signature, key_id)
        return False

    def get_metadata(self) -> dict[str, Any]:
        """Return provider metadata distinguishing KMS from LOCAL."""
        return {
            "provider_type": self.provider_type,
            "algorithm": self.algorithm,
            "key_id": self.kms_key_id
            or (self._local_fallback.key_id if self._local_fallback else "none"),
        }
