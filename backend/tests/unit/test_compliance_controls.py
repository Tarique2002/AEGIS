"""Unit tests for standard Compliance Controls."""

import pytest
from app.compliance.controls import get_standard_controls


@pytest.mark.asyncio
async def test_standard_controls_defined() -> None:
    controls = get_standard_controls()
    assert len(controls) >= 10

    control_ids = [c.control_id for c in controls]
    assert "AUTH-001" in control_ids
    assert "AUTH-004" in control_ids
    assert "SEC-001" in control_ids
    assert "AUD-001" in control_ids
    assert "AUD-002" in control_ids
    assert "POL-001" in control_ids
