"""Hermes-2-Pro tool-call parser.

Hermes-2-Pro and Hermes-3 emit tool calls inside `<tool_call>...</tool_call>`
tags containing JSON like:

    <tool_call>
    {"name": "fs.read", "arguments": {"path": "/etc/hosts"}}
    </tool_call>

The model finishes a turn either with another tool call or with free-form
text. A final answer can optionally be wrapped in `<final>...</final>` for
unambiguous extraction; we accept both.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
_FINAL_RE = re.compile(r"<final>(.*?)</final>", re.DOTALL)


@dataclass(slots=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class ParseResult:
    tool_calls: list[ToolCall]
    final: str | None
    raw: str


def parse(text: str) -> ParseResult:
    calls: list[ToolCall] = []
    for m in _TOOL_CALL_RE.finditer(text):
        try:
            obj = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        name = obj.get("name")
        args = obj.get("arguments", {})
        if isinstance(name, str) and isinstance(args, dict):
            calls.append(ToolCall(name=name, arguments=args))

    final: str | None = None
    fm = _FINAL_RE.search(text)
    if fm:
        final = fm.group(1).strip()
    elif not calls:
        # No tool calls and no <final> tag — treat the whole text as the
        # final answer. This matches Hermes-2-Pro's behavior when it's
        # confident enough to skip the explicit tag.
        final = text.strip()
    return ParseResult(tool_calls=calls, final=final, raw=text)


def render_tool_response(name: str, content: str) -> str:
    """Format a tool result the way Hermes-2-Pro expects to see it back."""
    return f"<tool_response>\n{json.dumps({'name': name, 'content': content})}\n</tool_response>"
