"""Tests for hermes.mcp_servers.shell."""
import sys
import pytest
from fastapi import HTTPException
from hermes.mcp_servers.shell import ShellServer


@pytest.fixture
def shell() -> ShellServer:
    return ShellServer()


@pytest.mark.asyncio
class TestShellExec:
    async def test_echo_command(self, shell: ShellServer):
        result = await shell.call("exec", {"command": "echo hello"})
        assert "hello" in result

    async def test_multiline_output(self, shell: ShellServer):
        result = await shell.call("exec", {"command": "printf 'a\\nb\\nc'"})
        assert "a" in result and "b" in result

    async def test_stderr_captured_in_output(self, shell: ShellServer):
        result = await shell.call("exec", {"command": "echo err >&2"})
        assert "err" in result

    async def test_nonzero_exit_still_returns_output(self, shell: ShellServer):
        # Shell errors return output, not exceptions
        result = await shell.call("exec", {"command": "echo before; exit 1; echo after"})
        assert "before" in result

    async def test_timeout_raises_408(self, shell: ShellServer):
        with pytest.raises(HTTPException) as exc:
            await shell.call("exec", {"command": "sleep 10", "timeout_seconds": 0.1})
        assert exc.value.status_code == 408

    async def test_unknown_op_raises_400(self, shell: ShellServer):
        with pytest.raises(HTTPException) as exc:
            await shell.call("run", {"command": "echo x"})
        assert exc.value.status_code == 400

    async def test_cwd_respected(self, shell: ShellServer, tmp_path):
        result = await shell.call("exec", {"command": "pwd", "cwd": str(tmp_path)})
        # Resolve symlinks (macOS /var -> /private/var)
        import os
        assert os.path.realpath(result.strip()) == os.path.realpath(str(tmp_path))
