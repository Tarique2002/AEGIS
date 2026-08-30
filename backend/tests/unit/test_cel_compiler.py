"""Unit tests for CELCompiler compilation and validation."""

import pytest
from app.authz.cel.compiler import CELCompiler
from app.authz.cel.errors import CELCompilationError


@pytest.mark.asyncio
async def test_cel_compiler_valid_expressions() -> None:
    compiler = CELCompiler()

    res1 = compiler.compile("subject.tenant_id == resource.tenant_id")
    assert res1.valid is True
    assert res1.ast is not None

    res2 = compiler.compile("'admin' in subject.roles && action == 'delete'")
    assert res2.valid is True

    res3 = compiler.compile(
        "resource.sensitivity != 'critical' || 'security:read' in subject.permissions"
    )
    assert res3.valid is True


@pytest.mark.asyncio
async def test_cel_compiler_invalid_syntax() -> None:
    compiler = CELCompiler()

    res = compiler.compile("subject.tenant_id == == invalid syntax")
    assert res.valid is False
    assert len(res.errors) > 0

    with pytest.raises(CELCompilationError):
        compiler.validate_or_raise("invalid +++ syntax")
