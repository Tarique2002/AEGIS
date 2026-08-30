"""Unit tests for LocalSigningProvider and KMSSigningProvider."""

import pytest
from app.security.signing.kms import KMSSigningProvider
from app.security.signing.local import LocalSigningProvider


@pytest.mark.asyncio
async def test_local_signing_provider_sign_and_verify() -> None:
    provider = LocalSigningProvider()
    payload = b"test:payload:12345"

    signature, key_id = provider.sign(payload)
    assert len(signature) == 64
    assert key_id == provider.key_id

    # Verify matching payload
    assert provider.verify(payload, signature, key_id) is True

    # Verify tampered payload fails
    assert provider.verify(b"tampered:payload", signature, key_id) is False

    # Verify wrong key ID fails
    assert provider.verify(payload, signature, "wrong-key-id") is False


@pytest.mark.asyncio
async def test_kms_signing_provider_fallback_to_local() -> None:
    # In offline dev/test environment without AEGIS_KMS_KEY_ID, provider defaults to local fallback
    kms_provider = KMSSigningProvider(kms_key_id=None, fallback_local=True)
    metadata = kms_provider.get_metadata()
    assert metadata["provider_type"] == "LOCAL"

    payload = b"kms:test:payload"
    signature, key_id = kms_provider.sign(payload)
    assert kms_provider.verify(payload, signature, key_id) is True
