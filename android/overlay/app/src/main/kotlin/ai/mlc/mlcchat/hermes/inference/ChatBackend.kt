package ai.mlc.mlcchat.hermes.inference

import ai.mlc.mlcchat.hermes.agent.HermesAgentLoop

/**
 * Pluggable chat backend. Concrete impls:
 *   - MlcChatBackend: local MLC LLM (Qwen2.5-Coder 3B on the S24)
 *   - RemoteChatBackend: dispatch over Tailscale to a laptop daemon (v0.2)
 *
 * The agent loop only needs `chat`; everything else (loading, warmup,
 * health checks) is the backend's concern.
 */
interface ChatBackend {
    val name: String

    /** Cheap probe — does this backend look usable right now? */
    suspend fun isAvailable(): Boolean

    /** One-shot chat completion. Non-streaming so the parser sees a complete tool call. */
    suspend fun chat(messages: List<HermesAgentLoop.Message>): String
}
