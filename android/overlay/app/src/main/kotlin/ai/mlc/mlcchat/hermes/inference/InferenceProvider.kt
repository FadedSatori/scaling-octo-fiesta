package ai.mlc.mlcchat.hermes.inference

import ai.mlc.mlcchat.hermes.agent.HermesAgentLoop
import android.content.Context
import android.util.Log

/**
 * Picks a backend per call based on context size and availability. Order
 * of preference: remote (if configured & context above threshold) ->
 * local MLC. Falls through on failure.
 */
class InferenceProvider(
    private val cfg: HermesConfig,
    private val local: ChatBackend,
    private val remote: ChatBackend?,
) {
    suspend fun chat(messages: List<HermesAgentLoop.Message>): String {
        val ctxSize = messages.sumOf { it.content.length }
        val ordered = chooseOrder(ctxSize)
        var lastError: Throwable? = null
        for (backend in ordered) {
            if (!backend.isAvailable()) continue
            try {
                return backend.chat(messages)
            } catch (t: Throwable) {
                Log.w(TAG, "backend ${backend.name} failed: ${t.message}", t)
                lastError = t
            }
        }
        throw IllegalStateException("no chat backend produced a response", lastError)
    }

    private fun chooseOrder(ctxSize: Int): List<ChatBackend> {
        val preferRemote = remote != null
                && cfg.remoteContextThreshold > 0
                && ctxSize >= cfg.remoteContextThreshold
        return if (preferRemote && remote != null) listOf(remote, local) else listOfNotNull(local, remote)
    }

    companion object {
        private const val TAG = "Hermes/Inference"

        fun fromConfig(ctx: Context, cfg: HermesConfig): InferenceProvider {
            val local = MlcChatBackend(ctx, cfg)
            val remote = if (cfg.remoteUrl.isNotBlank()) RemoteChatBackend(cfg) else null
            return InferenceProvider(cfg, local, remote)
        }
    }
}
