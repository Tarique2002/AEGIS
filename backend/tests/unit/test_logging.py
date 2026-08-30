"""Unit tests for structured logging and secret masking."""

import json
import logging

from app.core.logging import MASK_VALUE, JSONFormatter, mask_sensitive_data


def test_mask_sensitive_data_dict():
    raw_data = {
        "user_id": "123",
        "api_key": "sk-proj-supersecretkey",
        "nested": {
            "password": "secret_password",
            "token": "bearer_jwt_xyz",
            "safe_metric": 42,
        },
        "items": [
            {"secret_field": "confidential"},
            {"public_field": "visible"},
        ],
    }

    masked = mask_sensitive_data(raw_data)

    assert masked["user_id"] == "123"
    assert masked["api_key"] == MASK_VALUE
    assert masked["nested"]["password"] == MASK_VALUE
    assert masked["nested"]["token"] == MASK_VALUE
    assert masked["nested"]["safe_metric"] == 42
    assert masked["items"][0]["secret_field"] == MASK_VALUE
    assert masked["items"][1]["public_field"] == "visible"


def test_json_formatter_output():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="aegis.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Task initiated successfully",
        args=(),
        exc_info=None,
    )
    record.task_id = "test-task-uuid"
    record.request_id = "req-1234"

    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "aegis.test"
    assert parsed["message"] == "Task initiated successfully"
    assert parsed["task_id"] == "test-task-uuid"
    assert parsed["request_id"] == "req-1234"
    assert "timestamp" in parsed
