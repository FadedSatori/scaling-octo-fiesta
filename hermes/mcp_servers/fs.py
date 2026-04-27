"""Sandboxed filesystem MCP server.

Operations are restricted to a configured allowlist of root directories. Any
path that resolves outside the roots is rejected.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class ReadReq(BaseModel):
    path: str
    max_bytes: int = 256_000


class WriteReq(BaseModel):
    path: str
    content: str
    create_parents: bool = True


class ListReq(BaseModel):
    path: str


class FsServer:
    name = "fs"
    ops = ("read", "write", "list")

    def __init__(self, *, roots: list[Path]) -> None:
        self.roots = [r.resolve() for r in roots]

    def _resolve(self, p: str) -> Path:
        candidate = Path(p).resolve()
        if not self.roots:
            raise HTTPException(403, "no fs roots configured")
        if not any(_is_under(candidate, root) for root in self.roots):
            raise HTTPException(403, f"path '{p}' is outside allowed roots")
        return candidate

    async def call(self, op: str, args: dict[str, Any]) -> str:
        if op == "read":
            req = ReadReq.model_validate(args)
            path = self._resolve(req.path)
            data = path.read_bytes()[: req.max_bytes]
            return data.decode("utf-8", errors="replace")
        if op == "write":
            req = WriteReq.model_validate(args)
            path = self._resolve(req.path)
            if req.create_parents:
                path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(req.content, encoding="utf-8")
            return f"wrote {len(req.content)} chars to {path}"
        if op == "list":
            req = ListReq.model_validate(args)
            path = self._resolve(req.path)
            entries = []
            for child in sorted(path.iterdir()):
                kind = "d" if child.is_dir() else "f"
                entries.append(f"{kind} {child.name}")
            return "\n".join(entries)
        raise HTTPException(400, f"unknown op '{op}'")

    def mount(self, app: FastAPI, *, prefix: str) -> None:
        @app.post(f"{prefix}/read")
        async def _read(req: ReadReq) -> dict:
            return {"content": await self.call("read", req.model_dump())}

        @app.post(f"{prefix}/write")
        async def _write(req: WriteReq) -> dict:
            return {"result": await self.call("write", req.model_dump())}

        @app.post(f"{prefix}/list")
        async def _list(req: ListReq) -> dict:
            return {"entries": (await self.call("list", req.model_dump())).splitlines()}


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
