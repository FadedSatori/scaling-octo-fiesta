package ai.mlc.mlcchat.hermes.agent

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class HermesParserTest {

    @Test
    fun `single tool call is parsed`() {
        val text = """
            Some preamble.
            <tool_call>
            {"name": "fs.read", "arguments": {"path": "/etc/hosts"}}
            </tool_call>
        """.trimIndent()
        val result = HermesParser.parse(text)
        assertEquals(1, result.toolCalls.size)
        assertEquals("fs.read", result.toolCalls[0].name)
        assertNull(result.final)
    }

    @Test
    fun `final tag is extracted`() {
        val text = "<final>The answer is 42.</final>"
        val result = HermesParser.parse(text)
        assertEquals("The answer is 42.", result.final)
        assertTrue(result.toolCalls.isEmpty())
    }

    @Test
    fun `plain text with no tags becomes final`() {
        val text = "Just a plain answer."
        val result = HermesParser.parse(text)
        assertEquals("Just a plain answer.", result.final)
        assertTrue(result.toolCalls.isEmpty())
    }

    @Test
    fun `malformed json inside tool_call is ignored`() {
        val text = "<tool_call>{not valid json}</tool_call>"
        val result = HermesParser.parse(text)
        assertTrue(result.toolCalls.isEmpty())
        // No tool calls + no <final> tag → raw text treated as final
        assertNotNull(result.final)
    }

    @Test
    fun `multiple tool calls in one response`() {
        val text = """
            <tool_call>{"name":"fs.list","arguments":{"path":"/tmp"}}</tool_call>
            <tool_call>{"name":"shell.exec","arguments":{"command":"echo hi"}}</tool_call>
        """.trimIndent()
        val result = HermesParser.parse(text)
        assertEquals(2, result.toolCalls.size)
        assertEquals("fs.list", result.toolCalls[0].name)
        assertEquals("shell.exec", result.toolCalls[1].name)
        // tool calls present + no <final> tag → final is null
        assertNull(result.final)
    }

    @Test
    fun `render tool response contains expected fragments`() {
        val rendered = HermesParser.renderToolResponse("fs.read", "file contents here")
        assertTrue(rendered.contains("<tool_response>"))
        assertTrue(rendered.contains("fs.read"))
        assertTrue(rendered.contains("file contents here"))
    }

    @Test
    fun `tool call with missing arguments defaults to empty object`() {
        val text = """<tool_call>{"name":"shell.exec"}</tool_call>"""
        val result = HermesParser.parse(text)
        assertEquals(1, result.toolCalls.size)
        assertEquals("shell.exec", result.toolCalls[0].name)
        assertTrue(result.toolCalls[0].arguments.isEmpty())
    }

    @Test
    fun `final tag content is trimmed`() {
        val text = "<final>  spaces around  </final>"
        val result = HermesParser.parse(text)
        assertEquals("spaces around", result.final)
    }
}
