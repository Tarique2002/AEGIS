"""Data sanitization utilities for execution trajectories and learning signals."""

import re
from typing import Any

SENSITIVE_KEY_PATTERNS = [
    re.compile(r"pass(word)?", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"auth(orization)?", re.IGNORECASE),
    re.compile(r"bearer", re.IGNORECASE),
    re.compile(r"cookie", re.IGNORECASE),
    re.compile(r"private[_-]?key", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
]

SECRET_REPLACEMENT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(bearer\s+)[a-zA-Z0-9_\-\.]{15,}", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    (
        re.compile(r"ey[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}"),
        "[REDACTED_JWT]",
    ),
    (re.compile(r"(?:sk|pk|api)[_-][a-zA-Z0-9_\-]{10,}", re.IGNORECASE), "[REDACTED_API_KEY]"),
    (
        re.compile(r"(api[_\-\s]?key[\"'\s:=]+)[a-zA-Z0-9_\-\.]{10,}", re.IGNORECASE),
        r"\1[REDACTED_API_KEY]",
    ),
    (
        re.compile(r"((?:--?|/)?(?:pass(?:word)?|passwd)[\"'\s:=]+)[^\s\"',;&]+", re.IGNORECASE),
        r"\1[REDACTED_PASSWORD]",
    ),
    (re.compile(r"(secret[\"'\s:=]+)[^\s\"',;&]+", re.IGNORECASE), r"\1[REDACTED_SECRET]"),
    (
        re.compile(r"([a-zA-Z0-9\+\.\-]+://[^:/@]+:)([^@]+)(@)", re.IGNORECASE),
        r"\1[REDACTED_DB_PW]\3",
    ),
    (
        re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[^-]+-----END [A-Z ]+ PRIVATE KEY-----"),
        "[REDACTED_PRIVATE_KEY]",
    ),
]

MASKED_VALUE = "[REDACTED_SECRET]"


def is_sensitive_key(key: str) -> bool:
    """Check whether a dict key implies sensitive contents."""
    return any(pattern.search(key) is not None for pattern in SENSITIVE_KEY_PATTERNS)


def sanitize_string(text: str) -> str:
    """Replace sensitive patterns in freeform strings with masked markers."""
    sanitized = text
    for pattern, replacement in SECRET_REPLACEMENT_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def sanitize_data(data: Any) -> Any:
    """
    Recursively sanitize dictionaries, lists, and primitives,
    redacting known secret keys and token-like substrings.
    """
    if isinstance(data, dict):
        cleaned: dict[str, Any] = {}
        for k, v in data.items():
            if is_sensitive_key(str(k)):
                cleaned[k] = MASKED_VALUE
            else:
                cleaned[k] = sanitize_data(v)
        return cleaned

    if isinstance(data, list):
        return [sanitize_data(item) for item in data]

    if isinstance(data, tuple):
        return tuple(sanitize_data(item) for item in data)

    if isinstance(data, str):
        return sanitize_string(data)

    return data
