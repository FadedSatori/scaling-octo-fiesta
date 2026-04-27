package ai.mlc.mlcchat.hermes.agent

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * Hermes-2-Pro / Hermes-3 tool-call parser.
 *
 * Mirrors hermes/agent/parser.py on the laptop side so behaviour is identical.
 */
data class ToolCall(val name: String, val arguments: JsonObject)
data class ParseResult(val toolCalls: List<ToolCall>, val final: String?, val raw: String)

object HermesParser {

    private val toolCallRe =
        Regex("""<tool_call>\s*(\{.*?\})\s*</tool_call>""", setOf(RegexOption.DOT_MATCHES_ALL))
    private val finalRe = Regex("""<final>(.*?)</final>""", RegexOption.DOT_MATCHES_ALL)
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    fun parse(text: String): ParseResult {
        val calls = mutableListOf<ToolCall>()
        toolCallRe.findAll(text).forEach { m ->
            try {
                val obj: JsonElement = json.parseToJsonElement(m.groupValues[1])
                val o = obj.jsonObject
                val name = o["name"]?.jsonPrimitive?.content ?: return@forEach
                val args = o["arguments"]?.jsonObject ?: JsonObject(emptyMap())
                calls.add(ToolCall(name, args))
            } catch (_: Exception) { /* ignore malformed call */ }
        }
        val finalMatch = finalRe.find(text)
        val final = when {
            finalMatch != null -> finalMatch.groupValues[1].trim()
            calls.isEmpty() -> text.trim()
            else -> null
        }
        return ParseResult(calls, final, text)
    }

    fun renderToolResponse(name: String, content: String): String {
        val payload = JsonObject(mapOf(
            "name" to kotlinx.serialization.json.JsonPrimitive(name),
            "content" to kotlinx.serialization.json.JsonPrimitive(content),
        ))
        return "<tool_response>\n${json.encodeToString(JsonElement.serializer(), payload)}\n</tool_response>"
    }
}
