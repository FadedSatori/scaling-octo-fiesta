"""Inference MCP server. Wraps Ollama with a Hermes-2-Pro-aware chat call."""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class ChatReq(BaseModel):
    model: str | None = None
    messages: list[dict[str, Any]]


class InferenceServer:
    name = "inference"
    ops = ("chat",)

    def __init__(self, *, ollama_url: str, coder_model: str, agent_model: str) -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.coder_model = coder_model
        self.agent_model = agent_model
        self._client = httpx.AsyncClient(timeout=300.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat(self, *, model: str, messages: list[dict[str, Any]]) -> str:
        r = await self._client.post(
            f"{self.ollama_url}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
        )
        r.raise_for_status()
        return r.json()["message"]["content"]

    async def call(self, op: str, args: dict[str, Any]) -> str:
        if op != "chat":
            raise HTTPException(400, f"unknown op '{op}'")
        req = ChatReq.model_validate(args)
        return await self.chat(model=req.model or self.agent_model, messages=req.messages)

    def mount(self, app: FastAPI, *, prefix: str) -> None:
        @app.post(f"{prefix}/chat")
        async def _chat(req: ChatReq) -> dict:
            return {"content": await self.call("chat", req.model_dump())}
