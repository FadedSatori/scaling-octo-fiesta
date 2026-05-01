package ai.mlc.mlcchat.hermes.agent

import ai.mlc.mlcchat.hermes.mcp.ToolNamespace
import ai.mlc.mlcchat.hermes.mcp.ToolRegistry
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.JsonObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class HermesAgentLoopTest {

    /** Tool that echoes back the 'message' argument value. */
    private class EchoTool : ToolNamespace {
        override val name = "echo"
        override val ops = listOf("say")
        override suspend fun call(op: String, args: JsonObject): String {
            if (op != "say") return "error: unknown op '$op'"
            return args["message"]?.let {
                kotlinx.serialization.json.Json.decodeFromJsonElement(
                    kotlinx.serialization.json.JsonPrimitive.serializer(), it
                ).content
            } ?: "no message"
        }
    }

    private fun makeLoop(responses: List<String>): HermesAgentLoop {
        val queue = ArrayDeque(responses)
        return HermesAgentLoop(
            tools = ToolRegistry(mapOf("echo" to EchoTool())),
            infer = { _ -> queue.removeFirst() },
        )
    }

    @Test
    fun `direct final answer terminates in one step`() = runBlocking {
        val loop = makeLoop(listOf("<final>done</final>"))
        val run = loop.run("hello", maxSteps = 4)
        assertEquals("done", run.final)
        assertEquals(1, run.steps)
    }

    @Test
    fun `plain text response becomes final in one step`() = runBlocking {
        val loop = makeLoop(listOf("Just a straightforward answer."))
        val run = loop.run("question", maxSteps = 4)
        assertEquals("Just a straightforward answer.", run.final)
        assertEquals(1, run.steps)
    }

    @Test
    fun `tool call followed by final answer terminates in two steps`() = runBlocking {
        val toolCallResponse = """
            <tool_call>
            {"name":"echo.say","arguments":{"message":"ping"}}
            </tool_call>
        """.trimIndent()
        val finalResponse = "<final>pong</final>"
        val loop = makeLoop(listOf(toolCallResponse, finalResponse))
        val run = loop.run("test", maxSteps = 4)
        assertEquals("pong", run.final)
        assertEquals(2, run.steps)
        // Transcript: assistant (tool call) + tool (response) + assistant (final)
        val toolStep = run.transcript.firstOrNull { it.role == "tool" }
        assertNotNull(toolStep)
        assertEquals("ping", toolStep.content)
        assertEquals("echo.say", toolStep.toolName)
    }

    @Test
    fun `max steps reached returns null final`() = runBlocking {
        val infiniteToolCall = """
            <tool_call>{"name":"echo.say","arguments":{"message":"x"}}</tool_call>
        """.trimIndent()
        val loop = makeLoop(List(5) { infiniteToolCall })
        val run = loop.run("test", maxSteps = 3)
        assertNull(run.final)
        assertEquals(3, run.steps)
    }

    @Test
    fun `unknown tool namespace returns error in transcript`() = runBlocking {
        val callUnknown = """
            <tool_call>{"name":"nonexistent.op","arguments":{}}</tool_call>
        """.trimIndent()
        val loop = makeLoop(listOf(callUnknown, "<final>ok</final>"))
        val run = loop.run("test", maxSteps = 4)
        assertEquals("ok", run.final)
        val toolStep = run.transcript.firstOrNull { it.role == "tool" }
        assertNotNull(toolStep)
        assertTrue(toolStep.content.startsWith("error:"),
            "Expected error response, got: ${toolStep.content}")
    }

    @Test
    fun `tool call and final in same response — returns final after dispatching tools`() = runBlocking {
        // The loop processes tool calls first, then sees final != null and returns.
        val combined = """
            <tool_call>{"name":"echo.say","arguments":{"message":"hi"}}</tool_call>
            <final>combined answer</final>
        """.trimIndent()
        val loop = makeLoop(listOf(combined))
        val run = loop.run("test", maxSteps = 4)
        assertEquals("combined answer", run.final)
        assertEquals(1, run.steps)
        // Tool should still have been dispatched
        assertTrue(run.transcript.any { it.role == "tool" })
    }

    @Test
    fun `empty tool registry returns error for any namespace`() = runBlocking {
        val emptyLoop = HermesAgentLoop(
            tools = ToolRegistry(emptyMap()),
            infer = { msgs ->
                if (msgs.any { it.role == "tool" }) "<final>done</final>"
                else """<tool_call>{"name":"fs.read","arguments":{"path":"/tmp"}}</tool_call>"""
            },
        )
        val run = emptyLoop.run("test", maxSteps = 4)
        assertEquals("done", run.final)
        val toolStep = run.transcript.firstOrNull { it.role == "tool" }
        assertNotNull(toolStep)
        assertTrue(toolStep.content.startsWith("error:"))
    }
}
