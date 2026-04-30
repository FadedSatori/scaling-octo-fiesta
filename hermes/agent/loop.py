"""Hermes agent loop: prompt -> tool call -> response -> repeat -> final."""
from __future__ import annotations

import logging
from typing import Any, Protocol

from fastapi import FastAPI
from pydantic import BaseModel

from hermes.agent.parser import ParseResult, ToolCall, parse, render_tool_response

log = logging.getLogger("hermes.agent")


class InferenceLike(Protocol):
    async def chat(self, *, model: str, messages: list[dict[str, Any]]) -> str: ...
    @property
    def agent_model(self) -> str: ...


class ToolLike(Protocol):
    name: str
    async def call(self, op: str, arguments: dict[str, Any]) -> str: ...


SYSTEM_PROMPT = """\
You are Hermes, a local-first coding and desktop agent.

You can call tools by emitting:

<tool_call>
{"name": "<namespace>.<op>", "arguments": {...}}
</tool_call>

Tool results come back as <tool_response> blocks. After enough information,
emit your final answer wrapped in <final>...</final>. Be concise. Do not
fabricate tool results.

Available tool namespaces and their ops are listed under "Tools" in the
opening user message; only call ops listed there.
"""


class RunRequest(BaseModel):
    prompt: str
    max_steps: int = 8


class RunResponse(BaseModel):
    final: str | None
    steps: int
    transcript: list[dict[str, Any]]


class AgentLoop:
    def __init__(self, *, inference: InferenceLike, tools: dict[str, ToolLike]) -> None:
        self.inference = inference
        self.tools = tools

    def _tool_manifest(self) -> str:
        lines = ["Tools:"]
        for ns, tool in self.tools.items():
            ops = getattr(tool, "ops", None)
            if ops:
                lines.append(f"  {ns}: {', '.join(ops)}")
            else:
                lines.append(f"  {ns}")
        return "\n".join(lines)

    async def _dispatch(self, call: ToolCall) -> str:
        if "." not in call.name:
            return f"error: tool name '{call.name}' must be '<namespace>.<op>'"
        ns, op = call.name.split(".", 1)
        tool = self.tools.get(ns)
        if tool is None:
            return f"error: no such tool namespace '{ns}'"
        try:
            return await tool.call(op, call.arguments)
        except Exception as exc:  # noqa: BLE001 — surface to the model
            log.exception("tool dispatch failed: %s", call.name)
            return f"error: {type(exc).__name__}: {exc}"

    async def run(self, req: RunRequest) -> RunResponse:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + self._tool_manifest()},
            {"role": "user", "content": req.prompt},
        ]
        transcript: list[dict[str, Any]] = []

        for step in range(req.max_steps):
            text = await self.inference.chat(
                model=self.inference.agent_model, messages=messages
            )
            transcript.append({"role": "assistant", "content": text})
            parsed: ParseResult = parse(text)

            if parsed.final is not None and not parsed.tool_calls:
                return RunResponse(final=parsed.final, steps=step + 1, transcript=transcript)

            messages.append({"role": "assistant", "content": text})

            for call in parsed.tool_calls:
                result = await self._dispatch(call)
                rendered = render_tool_response(call.name, result)
                transcript.append({"role": "tool", "name": call.name, "content": result})
                messages.append({"role": "tool", "name": call.name, "content": rendered})

            if parsed.final is not None:
                return RunResponse(final=parsed.final, steps=step + 1, transcript=transcript)

        return RunResponse(final=None, steps=req.max_steps, transcript=transcript)

    def mount(self, app: FastAPI, *, prefix: str) -> None:
        @app.post(f"{prefix}/run", response_model=RunResponse)
        async def _run(req: RunRequest) -> RunResponse:
            return await self.run(req)
