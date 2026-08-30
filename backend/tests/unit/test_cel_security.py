"""Unit tests proving CEL sandbox safety and rejection of dangerous Python patterns."""

import pytest
from app.authz.cel.compiler import CELCompiler


@pytest.mark.asyncio
async def test_cel_rejects_dunder_methods() -> None:
    compiler = CELCompiler()
    res = compiler.compile("subject.__class__.__bases__")
    assert res.valid is False
    assert any("disallowed pattern" in err for err in res.errors)


@pytest.mark.asyncio
async def test_cel_rejects_import_and_exec() -> None:
    compiler = CELCompiler()

    res_import = compiler.compile("import os")
    assert res_import.valid is False

    res_eval = compiler.compile("eval('1+1')")
    assert res_eval.valid is False

    res_exec = compiler.compile("exec('print(1)')")
    assert res_exec.valid is False


@pytest.mark.asyncio
async def test_cel_rejects_subprocess_and_os() -> None:
    compiler = CELCompiler()

    res_sub = compiler.compile("subprocess.Popen(['ls'])")
    assert res_sub.valid is False

    res_os = compiler.compile("os.system('id')")
    assert res_os.valid is False
