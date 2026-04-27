package ai.mlc.mlcchat.hermes.agent

import ai.mlc.mlcchat.hermes.mcp.ToolRegistry
import kotlinx.serialization.json.JsonObject

/**
 * Iterative tool-call loop matching the Python implementation in
 * `hermes/agent/loop.py`. Pure Kotlin — no Android deps so it can be unit-tested
 * on the JVM.
 *
 * `infer` is the bridge to whatever inference backend is wired up at runtime
 * (MLC for the bundled Qwen2.5-Coder, or a remote dispatch over Tailscale).
 */
class HermesAgentLoop(
    private val tools: ToolRegistry,
    private val infer: suspend (messages: List<Message>) -> String,
    private val systemPrompt: String = DEFAULT_SYSTEM_PROMPT,
) {

    data class Message(val role: String, val content: String)
    data class StepLog(val role: String, val content: String, val toolName: String? = null)
    data class Run(val final: String?, val steps: Int, val transcript: List<StepLog>)

    suspend fun run(prompt: String, maxSteps: Int = 8): Run {
        val transcript = mutableListOf<StepLog>()
        val msgs = mutableListOf(
            Message("system", "$systemPrompt\n\n${tools.manifest()}"),
            Message("user", prompt),
        )
        for (step in 0 until maxSteps) {
            val text = infer(msgs)
            transcript += StepLog("assistant", text)
            val parsed = HermesParser.parse(text)

            if (parsed.final != null && parsed.toolCalls.isEmpty()) {
                return Run(parsed.final, step + 1, transcript)
            }
            msgs += Message("assistant", text)

            for (call in parsed.toolCalls) {
                val result = dispatch(call.name, call.arguments)
                transcript += StepLog("tool", result, toolName = call.name)
                msgs += Message("tool", HermesParser.renderToolResponse(call.name, result))
            }
            if (parsed.final != null) {
                return Run(parsed.final, step + 1, transcript)
            }
        }
        return Run(null, maxSteps, transcript)
    }

    private suspend fun dispatch(name: String, args: JsonObject): String {
        val dot = name.indexOf('.')
        if (dot <= 0) return "error: tool name '$name' must be '<namespace>.<op>'"
        val ns = name.substring(0, dot)
        val op = name.substring(dot + 1)
        val tool = tools.get(ns) ?: return "error: no such tool namespace '$ns'"
        return runCatching { tool.call(op, args) }.getOrElse { e ->
            "error: ${e::class.simpleName}: ${e.message}"
        }
    }

    companion object {
        const val DEFAULT_SYSTEM_PROMPT = """You are Hermes, a local-first coding and desktop agent running on a Samsung S24.

You can call tools by emitting:

<tool_call>
{"name": "<namespace>.<op>", "arguments": {...}}
</tool_call>

Tool results come back as <tool_response> blocks. After enough information,
emit your final answer wrapped in <final>...</final>. Be concise. Do not
fabricate tool results."""
    }
}
