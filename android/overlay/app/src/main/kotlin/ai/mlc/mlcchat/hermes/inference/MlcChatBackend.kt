package ai.mlc.mlcchat.hermes.inference

import ai.mlc.mlcchat.hermes.agent.HermesAgentLoop
import ai.mlc.mlcllm.MLCEngine
import ai.mlc.mlcllm.OpenAIProtocol.ChatCompletionMessage
import ai.mlc.mlcllm.OpenAIProtocol.ChatCompletionRequest
import ai.mlc.mlcllm.OpenAIProtocol.ChatCompletionRole
import android.content.Context
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

/**
 * Local MLC LLM backend. Loads Qwen2.5-Coder 3B Q4f16_1 (or whichever model
 * id is configured) once and reuses the engine for subsequent calls.
 *
 * Imports target the `mlc4j` library shipped inside the MLC Chat upstream
 * repo. Pin the upstream commit if MLC's API breaks — see
 * `android/overlay/MERGES.md` for the dependency declaration.
 */
class MlcChatBackend(
    private val ctx: Context,
    private val cfg: HermesConfig,
) : ChatBackend {

    override val name: String = "mlc-local:${cfg.modelId}"

    private val engine = MLCEngine()
    private val loadMutex = Mutex()
    @Volatile private var loaded = false

    override suspend fun isAvailable(): Boolean {
        if (!cfg.modelAbsolutePath(ctx).exists()) return false
        return runCatching { ensureLoaded() }.isSuccess
    }

    private suspend fun ensureLoaded() {
        if (loaded) return
        loadMutex.withLock {
            if (loaded) return
            val dir = cfg.modelAbsolutePath(ctx)
            require(dir.exists()) { "model dir missing: ${dir.absolutePath}" }
            withContext(Dispatchers.Default) {
                engine.reload(dir.absolutePath, cfg.modelLib)
            }
            loaded = true
            Log.i(TAG, "MLC engine loaded: ${cfg.modelId} from ${dir.absolutePath}")
        }
    }

    override suspend fun chat(messages: List<HermesAgentLoop.Message>): String {
        ensureLoaded()
        val request = ChatCompletionRequest(
            messages = messages.map { it.toMlc() },
            model = cfg.modelId,
            stream = true,
        )
        val sb = StringBuilder()
        withContext(Dispatchers.Default) {
            engine.chat.completions.create(request).collect { chunk ->
                chunk.choices.firstOrNull()?.delta?.content?.asText()?.let { sb.append(it) }
            }
        }
        return sb.toString()
    }

    companion object { private const val TAG = "Hermes/MLC" }
}

private fun HermesAgentLoop.Message.toMlc(): ChatCompletionMessage {
    val role = when (role) {
        "system" -> ChatCompletionRole.system
        "user" -> ChatCompletionRole.user
        "assistant" -> ChatCompletionRole.assistant
        "tool" -> ChatCompletionRole.tool
        else -> ChatCompletionRole.user
    }
    return ChatCompletionMessage(role = role, content = content)
}

/**
 * MLC's delta `content` is sometimes a String, sometimes a structured part
 * list depending on version. This adapter prefers the simple text path and
 * falls back to a stringified form. Keep this isolated so an MLC SDK bump
 * is a one-file change.
 */
private fun Any?.asText(): String? = when (this) {
    null -> null
    is String -> this
    is List<*> -> joinToString("") { (it as? String) ?: it.toString() }
    else -> toString()
}
