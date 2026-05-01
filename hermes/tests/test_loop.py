"""Tests for hermes.agent.loop."""
import pytest
from hermes.agent.loop import AgentLoop, RunRequest, RunResponse


class _FakeInference:
    """Returns responses from a queue; records all messages received."""
    def __init__(self, responses: list[str]) -> None:
        self._queue = list(responses)
        self.calls: list[list[dict]] = []
        self.agent_model = "fake-model"

    async def chat(self, *, model: str, messages: list[dict]) -> str:
        self.calls.append(list(messages))
        if not self._queue:
            raise RuntimeError("response queue exhausted")
        return self._queue.pop(0)


class _EchoTool:
    name = "echo"
    ops = ("say",)

    async def call(self, op: str, arguments: dict) -> str:
        if op == "say":
            return arguments.get("message", "")
        return f"error: unknown op '{op}'"


class _BrokenTool:
    name = "broken"
    ops = ("fail",)

    async def call(self, op: str, arguments: dict) -> str:
        raise ValueError("tool always fails")


def _make_loop(responses: list[str], tools: dict | None = None) -> AgentLoop:
    if tools is None:
        tools = {"echo": _EchoTool()}
    return AgentLoop(
        inference=_FakeInference(responses),
        tools=tools,
    )


@pytest.mark.asyncio
class TestAgentLoop:
    async def test_direct_final_answer(self):
        loop = _make_loop(["<final>done</final>"])
        resp = await loop.run(RunRequest(prompt="hi"))
        assert resp.final == "done"
        assert resp.steps == 1

    async def test_plain_text_is_final(self):
        loop = _make_loop(["Just a plain answer."])
        resp = await loop.run(RunRequest(prompt="hi"))
        assert resp.final == "Just a plain answer."
        assert resp.steps == 1

    async def test_tool_call_then_final(self):
        loop = _make_loop([
            '<tool_call>{"name": "echo.say", "arguments": {"message": "ping"}}</tool_call>',
            "<final>pong</final>",
        ])
        resp = await loop.run(RunRequest(prompt="test"))
        assert resp.final == "pong"
        assert resp.steps == 2
        tool_steps = [t for t in resp.transcript if t["role"] == "tool"]
        assert len(tool_steps) == 1
        assert tool_steps[0]["content"] == "ping"
        assert tool_steps[0]["name"] == "echo.say"

    async def test_max_steps_returns_none_final(self):
        infinite = '<tool_call>{"name": "echo.say", "arguments": {"message": "x"}}</tool_call>'
        loop = _make_loop([infinite] * 10)
        resp = await loop.run(RunRequest(prompt="test", max_steps=3))
        assert resp.final is None
        assert resp.steps == 3

    async def test_unknown_namespace_returns_error_string(self):
        loop = _make_loop([
            '<tool_call>{"name": "nope.op", "arguments": {}}</tool_call>',
            "<final>ok</final>",
        ])
        resp = await loop.run(RunRequest(prompt="test"))
        assert resp.final == "ok"
        tool_steps = [t for t in resp.transcript if t["role"] == "tool"]
        assert tool_steps[0]["content"].startswith("error:")

    async def test_malformed_tool_name_returns_error(self):
        loop = _make_loop([
            '<tool_call>{"name": "no-dot", "arguments": {}}</tool_call>',
            "<final>ok</final>",
        ])
        resp = await loop.run(RunRequest(prompt="test"))
        tool_steps = [t for t in resp.transcript if t["role"] == "tool"]
        assert "error:" in tool_steps[0]["content"]

    async def test_broken_tool_error_surfaced(self):
        loop = _make_loop(
            [
                '<tool_call>{"name": "broken.fail", "arguments": {}}</tool_call>',
                "<final>ok</final>",
            ],
            tools={"broken": _BrokenTool()},
        )
        resp = await loop.run(RunRequest(prompt="test"))
        tool_steps = [t for t in resp.transcript if t["role"] == "tool"]
        assert "ValueError" in tool_steps[0]["content"]

    async def test_tool_call_and_final_in_same_response(self):
        loop = _make_loop([
            '<tool_call>{"name": "echo.say", "arguments": {"message": "hi"}}</tool_call>'
            "<final>combined</final>",
        ])
        resp = await loop.run(RunRequest(prompt="test"))
        assert resp.final == "combined"
        assert resp.steps == 1
        assert any(t["role"] == "tool" for t in resp.transcript)

    async def test_system_prompt_in_first_message(self):
        inf = _FakeInference(["<final>ok</final>"])
        loop = AgentLoop(inference=inf, tools={"echo": _EchoTool()})
        await loop.run(RunRequest(prompt="hi"))
        first_msg = inf.calls[0][0]
        assert first_msg["role"] == "system"
        assert "echo" in first_msg["content"]  # tool manifest present

    async def test_user_prompt_in_second_message(self):
        inf = _FakeInference(["<final>ok</final>"])
        loop = AgentLoop(inference=inf, tools={})
        await loop.run(RunRequest(prompt="my prompt"))
        second_msg = inf.calls[0][1]
        assert second_msg["role"] == "user"
        assert second_msg["content"] == "my prompt"

    async def test_tool_manifest_lists_all_ops(self):
        inf = _FakeInference(["<final>ok</final>"])
        loop = AgentLoop(inference=inf, tools={"echo": _EchoTool(), "broken": _BrokenTool()})
        await loop.run(RunRequest(prompt="hi"))
        system_content = inf.calls[0][0]["content"]
        assert "echo" in system_content
        assert "say" in system_content
        assert "broken" in system_content

    async def test_empty_tools_dict(self):
        loop = _make_loop(["<final>ok</final>"], tools={})
        resp = await loop.run(RunRequest(prompt="hi"))
        assert resp.final == "ok"

    async def test_multiple_tool_calls_in_one_step(self):
        loop = _make_loop([
            '<tool_call>{"name": "echo.say", "arguments": {"message": "a"}}</tool_call>'
            '<tool_call>{"name": "echo.say", "arguments": {"message": "b"}}</tool_call>',
            "<final>done</final>",
        ])
        resp = await loop.run(RunRequest(prompt="test"))
        tool_steps = [t for t in resp.transcript if t["role"] == "tool"]
        assert len(tool_steps) == 2
