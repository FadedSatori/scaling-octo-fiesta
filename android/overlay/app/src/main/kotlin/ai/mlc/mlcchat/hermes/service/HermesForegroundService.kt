package ai.mlc.mlcchat.hermes.service

import ai.mlc.mlcchat.hermes.agent.HermesAgentLoop
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
import io.ktor.server.engine.embeddedServer
import io.ktor.server.netty.Netty
import io.ktor.server.plugins.contentnegotiation.ContentNegotiation
import io.ktor.server.request.receive
import io.ktor.server.response.respond
import io.ktor.server.routing.get
import io.ktor.server.routing.post
import io.ktor.server.routing.routing
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable

/**
 * Foreground service hosting the Hermes HTTP/MCP server on
 * 127.0.0.1:8765 (Tailscale binding planned for v0.2).
 */
class HermesForegroundService : Service() {

    private val scope = CoroutineScope(SupervisorJob())
    private var serverJob: Job? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        startForeground(NOTIF_ID, buildNotification())

        val tools = ToolRegistry(mapOf(
            "fs" to FsTool(roots = listOf(
                Environment.getExternalStorageDirectory(),
                filesDir,
            )),
            "shell" to ShellTool(),
            "ui" to UiTool(),
            "app" to AppTool(),
        ))

        // Inference is wired up by InferenceBridge in v0.1; for now we delegate
        // to a stub that throws if called before the model is ready.
        val agent = HermesAgentLoop(tools, infer = ::stubInfer)

        serverJob = scope.launch {
            @Suppress("BlockingMethodInNonBlockingContext")
            embeddedServer(Netty, port = 8765, host = "127.0.0.1") {
                install(ContentNegotiation) { json() }
                routing {
                    get("/healthz") {
                        call.respond(mapOf("ok" to true, "device" to "s24", "version" to "0.1.0"))
                    }
                    post("/agent/run") {
                        val req = call.receive<RunReq>()
                        val r = agent.run(req.prompt, req.maxSteps)
                        call.respond(RunResp(r.final, r.steps))
                    }
                }
            }.start(wait = true)
        }
    }

    override fun onDestroy() {
        serverJob?.cancel()
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

    private suspend fun stubInfer(messages: List<HermesAgentLoop.Message>): String =
        error("inference bridge not yet wired up; v0.1 in progress")

    companion object {
        private const val CHANNEL = "hermes-fgs"
        private const val NOTIF_ID = 0xE3
    }

    @Serializable data class RunReq(val prompt: String, val maxSteps: Int = 8)
    @Serializable data class RunResp(val final: String?, val steps: Int)
}
