"""Structured logging with contextual tracing and secret masking."""

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings

# Patterns of sensitive keys to redact
SENSITIVE_KEY_PATTERNS = [
    re.compile(r"api[-_]?key", re.IGNORECASE),
    re.compile(r"pass(word)?", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"auth(orization)?", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
]

MASK_VALUE = "[REDACTED]"


def mask_sensitive_data(data: Any) -> Any:
    """Recursively mask sensitive values in dictionaries and lists."""
    if isinstance(data, dict):
        masked_dict = {}
        for key, value in data.items():
            if any(pattern.search(str(key)) for pattern in SENSITIVE_KEY_PATTERNS):
                masked_dict[key] = MASK_VALUE
            else:
                masked_dict[key] = mask_sensitive_data(value)
        return masked_dict
    elif isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]
    elif isinstance(data, str):
        # Redact Bearer tokens if present in strings
        if data.lower().startswith("bearer "):
            return f"Bearer {MASK_VALUE}"
        return data
    return data


class JSONFormatter(logging.Formatter):
    """Formats log records as structured JSON with UTC timestamp and context."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "environment": settings.ENVIRONMENT.value,
        }

        # Include custom contextual attributes if provided via extra
        context_fields = ["request_id", "task_id", "run_id", "step_id", "user_id"]
        for field in context_fields:
            if hasattr(record, field):
                log_payload[field] = getattr(record, field)

        # Include exception trace if present
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        # Mask sensitive keys in extra dictionary
        masked_payload = mask_sensitive_data(log_payload)
        return json.dumps(masked_payload)


class TextFormatter(logging.Formatter):
    """Human readable text formatter for local development."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f UTC")
        ctx = []
        for field in ["request_id", "task_id", "run_id"]:
            if hasattr(record, field):
                ctx.append(f"{field}={getattr(record, field)}")
        ctx_str = f" [{', '.join(ctx)}]" if ctx else ""
        header = f"[{timestamp}] [{record.levelname:<7}] [{record.name}]{ctx_str}"
        msg = f"{header} {record.getMessage()}"
        if record.exc_info:
            msg += f"\n{self.formatException(record.exc_info)}"
        return msg


def setup_logging() -> None:
    """Initialize root and app logging handlers."""
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL)

    # Clear existing handlers
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if settings.LOG_FORMAT == "json" and settings.ENVIRONMENT != "development":
        handler.setFormatter(JSONFormatter())
    elif settings.LOG_FORMAT == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(TextFormatter())

    root_logger.addHandler(handler)

    # Silence overly verbose external loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger."""
    return logging.getLogger(name)
