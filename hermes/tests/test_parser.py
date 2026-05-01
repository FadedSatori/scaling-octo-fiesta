"""Tests for hermes.agent.parser."""
import pytest
from hermes.agent.parser import parse, render_tool_response, ToolCall, ParseResult


class TestParse:
    def test_single_tool_call(self):
        text = '<tool_call>\n{"name": "fs.read", "arguments": {"path": "/etc/hosts"}}\n</tool_call>'
        r = parse(text)
        assert len(r.tool_calls) == 1
        assert r.tool_calls[0].name == "fs.read"
        assert r.tool_calls[0].arguments == {"path": "/etc/hosts"}
        assert r.final is None

    def test_multiple_tool_calls(self):
        text = (
            '<tool_call>{"name": "fs.list", "arguments": {"path": "/tmp"}}</tool_call>\n'
            '<tool_call>{"name": "shell.exec", "arguments": {"command": "pwd"}}</tool_call>'
        )
        r = parse(text)
        assert len(r.tool_calls) == 2
        assert r.tool_calls[0].name == "fs.list"
        assert r.tool_calls[1].name == "shell.exec"
        assert r.final is None

    def test_final_tag_extraction(self):
        r = parse("<final>The answer is 42.</final>")
        assert r.final == "The answer is 42."
        assert r.tool_calls == []

    def test_final_tag_whitespace_stripped(self):
        r = parse("<final>  spaces  </final>")
        assert r.final == "spaces"

    def test_plain_text_becomes_final(self):
        r = parse("Just a plain answer.")
        assert r.final == "Just a plain answer."
        assert r.tool_calls == []

    def test_plain_text_stripped(self):
        r = parse("  answer  ")
        assert r.final == "answer"

    def test_malformed_json_ignored(self):
        r = parse("<tool_call>{not valid json}</tool_call>")
        assert r.tool_calls == []
        assert r.final is not None  # treated as plain text

    def test_missing_arguments_defaults_to_empty_dict(self):
        r = parse('<tool_call>{"name": "shell.exec"}</tool_call>')
        assert len(r.tool_calls) == 1
        assert r.tool_calls[0].arguments == {}

    def test_missing_name_skipped(self):
        r = parse('<tool_call>{"arguments": {"x": 1}}</tool_call>')
        assert r.tool_calls == []

    def test_non_string_name_skipped(self):
        r = parse('<tool_call>{"name": 42, "arguments": {}}</tool_call>')
        assert r.tool_calls == []

    def test_non_dict_arguments_skipped(self):
        r = parse('<tool_call>{"name": "fs.read", "arguments": "not a dict"}</tool_call>')
        assert r.tool_calls == []

    def test_tool_call_with_final_tag(self):
        text = '<tool_call>{"name": "fs.read", "arguments": {}}</tool_call><final>done</final>'
        r = parse(text)
        assert len(r.tool_calls) == 1
        assert r.final == "done"

    def test_empty_string(self):
        r = parse("")
        assert r.tool_calls == []
        assert r.final == ""

    def test_multiline_tool_call(self):
        text = """<tool_call>
{
  "name": "fs.write",
  "arguments": {
    "path": "/tmp/test.txt",
    "content": "hello"
  }
}
</tool_call>"""
        r = parse(text)
        assert len(r.tool_calls) == 1
        assert r.tool_calls[0].name == "fs.write"
        assert r.tool_calls[0].arguments["content"] == "hello"

    def test_raw_preserved(self):
        text = "some text"
        r = parse(text)
        assert r.raw == text


class TestRenderToolResponse:
    def test_contains_tool_response_tags(self):
        out = render_tool_response("fs.read", "content here")
        assert "<tool_response>" in out
        assert "</tool_response>" in out

    def test_contains_name_and_content(self):
        out = render_tool_response("shell.exec", "output line")
        assert "shell.exec" in out
        assert "output line" in out

    def test_valid_json_inside(self):
        import json
        out = render_tool_response("fs.list", "a\nb\nc")
        inner = out.replace("<tool_response>", "").replace("</tool_response>", "").strip()
        data = json.loads(inner)
        assert data["name"] == "fs.list"
        assert data["content"] == "a\nb\nc"
