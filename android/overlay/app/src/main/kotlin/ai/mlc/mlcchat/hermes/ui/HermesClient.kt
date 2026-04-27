package ai.mlc.mlcchat.hermes.ui

import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/**
 * In-process HTTP client to the foreground service on 127.0.0.1:8765.
 * The service exposes the same wire shape as the laptop daemon, so this
 * client is reusable later for cross-device debugging.
 */
class HermesClient(private val baseUrl: String = "http://127.0.0.1:8765") {

    private val client = HttpClient(CIO) {
        install(ContentNegotiation) { json() }
        install(HttpTimeout) {
            requestTimeoutMillis = 5 * 60_000
            connectTimeoutMillis = 5_000
        }
    }
    private val json = Json { ignoreUnknownKeys = true }

    suspend fun health(): Health = json.decodeFromString(
        Health.serializer(), client.get("$baseUrl/healthz").bodyAsText()
    )

    suspend fun run(prompt: String, maxSteps: Int = 8): RunResp {
        val resp = client.post("$baseUrl/agent/run") {
            contentType(ContentType.Application.Json)
            setBody(RunReq(prompt, maxSteps))
        }
        return json.decodeFromString(RunResp.serializer(), resp.bodyAsText())
    }

    @Serializable data class Health(
        val ok: Boolean = false,
        val device: String = "",
        val version: String = "",
        val model: String = "",
    )
    @Serializable data class RunReq(val prompt: String, val maxSteps: Int = 8)
    @Serializable data class RunResp(val final: String? = null, val steps: Int = 0)
}
