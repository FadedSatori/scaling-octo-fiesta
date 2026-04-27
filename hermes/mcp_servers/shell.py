"""Shell MCP server. Runs PowerShell on Windows, /bin/sh elsewhere.

The server is unsandboxed by design — Hermes runs as a privileged service on
machines you own. The agent prompt and the device's Tailscale ACL are the
authorization boundary, not this code.
"""
from __future__ import annotations

import asyncio
import sys
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class ExecReq(BaseModel):
    command: str
    cwd: str | None = None
    timeout_seconds: float = 60.0


class ShellServer:
    name = "shell"
    ops = ("exec",)

    async def call(self, op: str, args: dict[str, Any]) -> str:
        if op != "exec":
            raise HTTPException(400, f"unknown op '{op}'")
        req = ExecReq.model_validate(args)
        if sys.platform == "win32":
            argv = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", req.command]
        else:
            argv = ["/bin/sh", "-c", req.command]
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=req.cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=req.timeout_seconds)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise HTTPException(408, f"command timed out after {req.timeout_seconds}s")
        return out.decode("utf-8", errors="replace")

    def mount(self, app: FastAPI, *, prefix: str) -> None:
        @app.post(f"{prefix}/exec")
        async def _exec(req: ExecReq) -> dict:
            return {"output": await self.call("exec", req.model_dump())}
