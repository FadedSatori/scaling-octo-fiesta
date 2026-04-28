package ai.mlc.mlcchat.hermes.service

import ai.mlc.mlcchat.hermes.agent.HermesAgentLoop
import ai.mlc.mlcchat.hermes.inference.HermesConfig
import ai.mlc.mlcchat.hermes.inference.InferenceProvider
import ai.mlc.mlcchat.hermes.mcp.AppTool
import ai.mlc.mlcchat.hermes.mcp.FsTool
import ai.mlc.mlcchat.hermes.mcp.ShellTool
import ai.mlc.mlcchat.hermes.mcp.ToolRegistry
import ai.mlc.mlcchat.hermes.mcp.UiTool
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.Environment
import android.os.IBinder
import io.ktor.serialization.kotlinx.json.json
import io.ktor.server.application.install
import io.ktor.server.cio.CIO
import io.ktor.server.engine.ApplicationEngine
import io.ktor.server.engine.embeddedServer
import io.ktor.server.plugins.contentnegotiation.ContentNegotiation
import io.ktor.server.request.receive
import io.ktor.server.response.respond
import io.ktor.server.routing.get
import io.ktor.server.routing.post
import io.ktor.server.routing.routing
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.serialization.Serializable

/**
 * Foreground service hosting the Hermes HTTP/MCP server on
 * 127.0.0.1:8765 (Tailscale binding planned for v0.2).
 */
class HermesForegroundService : Service() {

    private val scope = CoroutineScope(SupervisorJob())
    private var engine: ApplicationEngine? = null
    private lateinit var inference: InferenceProvider
    private lateinit var cfg: HermesConfig

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        startForeground(NOTIF_ID, buildNotification())

        cfg = HermesConfig.load(this)
        inference = InferenceProvider.fromConfig(this, cfg)

        val tools = ToolRegistry(mapOf(
            "fs" to FsTool(roots = listOf(
                Environment.getExternalStorageDirectory(),
                filesDir,
            )),
            "shell" to ShellTool(),
            "ui" to UiTool(),
            "app" to AppTool(),
        ))

        val agent = HermesAgentLoop(tools, infer = inference::chat)

        engine = embeddedServer(CIO, port = 8765, host = "127.0.0.1") {
            install(ContentNegotiation) { json() }
            routing {
                get("/healthz") {
                    call.respond(mapOf(
                        "ok" to true,
                        "device" to cfg.device,
                        "version" to "0.1.0",
                        "model" to cfg.modelId,
                    ))
                }
                post("/agent/run") {
                    val req = call.receive<RunReq>()
                    val r = agent.run(req.prompt, req.maxSteps)
                    call.respond(RunResp(r.final, r.steps))
                }
            }
        }.also { it.start(wait = false) }
    }

    override fun onDestroy() {
        engine?.stop(gracePeriodMillis = 1_000, timeoutMillis = 2_000)
        engine = null
        scope.cancel()
        super.onDestroy()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    private fun buildNotification(): Notification {
        val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        if (nm.getNotificationChannel(CHANNEL) == null) {
            nm.createNotificationChannel(NotificationChannel(
                CHANNEL, "Hermes", NotificationManager.IMPORTANCE_LOW))
        }
        return Notification.Builder(this, CHANNEL)
            .setContentTitle("Hermes is running")
            .setContentText("Local agent + MCP server")
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setOngoing(true)
            .build()
    }

    companion object {
        private const val CHANNEL = "hermes-fgs"
        private const val NOTIF_ID = 0xE3
    }

    @Serializable data class RunReq(val prompt: String, val maxSteps: Int = 8)
    @Serializable data class RunResp(val final: String?, val steps: Int)
}
