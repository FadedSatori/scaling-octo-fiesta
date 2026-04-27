package ai.mlc.mlcchat.hermes.inference

import ai.mlc.mlcchat.hermes.agent.HermesAgentLoop
import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/**
 * Dispatches to a laptop's Hermes daemon over Tailscale. Inactive in v0.1
 * (cfg.remoteUrl is empty); enabled once the laptops are bootstrapped and
 * the phone wants to offload large prompts.
 */
class RemoteChatBackend(
    private val cfg: HermesConfig,
    private val client: HttpClient = defaultClient(),
) : ChatBackend {

    override val name: String = "remote:${cfg.remoteUrl}"

    override suspend fun isAvailable(): Boolean {
        if (cfg.remoteUrl.isBlank()) return false
        return runCatching {
            client.post("${cfg.remoteUrl}/healthz")
                .status.value in 200..299
        }.getOrDefault(false)
    }

    override suspend fun chat(messages: List<HermesAgentLoop.Message>): String {
        val req = RemoteChatRequest(messages.map { RemoteMessage(it.role, it.content) })
        val resp = client.post("${cfg.remoteUrl}/mcp/inference/chat") {
            contentType(ContentType.Application.Json)
            setBody(req)
        }
        val body = resp.bodyAsText()
        return Json { ignoreUnknownKeys = true }
            .decodeFromString(RemoteChatResponse.serializer(), body).content
    }

    @Serializable private data class RemoteMessage(val role: String, val content: String)
    @Serializable private data class RemoteChatRequest(val messages: List<RemoteMessage>)
    @Serializable private data class RemoteChatResponse(val content: String)

    companion object {
        private fun defaultClient(): HttpClient = HttpClient(CIO) {
            install(ContentNegotiation) { json() }
            install(HttpTimeout) {
                requestTimeoutMillis = 5 * 60_000
                connectTimeoutMillis = 10_000
            }
        }
    }
}
