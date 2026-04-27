package ai.mlc.mlcchat.hermes.shizuku

import android.content.pm.PackageManager
import kotlinx.coroutines.suspendCancellableCoroutine
import rikka.shizuku.Shizuku
import kotlin.coroutines.resume

/**
 * Thin wrapper around the Shizuku API. Exposes:
 *   - permission state checks
 *   - a `suspend` permission request
 *   - a `shellExec` helper that runs commands as the `shell` user via Shizuku.
 *
 * The user installs Shizuku from the Play Store and pairs it via wireless
 * ADB once. Hermes never asks for root.
 */
object ShizukuClient {

    private const val REQ_CODE = 0xACE

    fun isInstalled(): Boolean = Shizuku.pingBinder()

    fun isGranted(): Boolean =
        isInstalled() && Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED

    suspend fun request(): Boolean = suspendCancellableCoroutine { cont ->
        if (isGranted()) {
            cont.resume(true); return@suspendCancellableCoroutine
        }
        val listener = object : Shizuku.OnRequestPermissionResultListener {
            override fun onRequestPermissionResult(requestCode: Int, grantResult: Int) {
                if (requestCode != REQ_CODE) return
                Shizuku.removeRequestPermissionResultListener(this)
                cont.resume(grantResult == PackageManager.PERMISSION_GRANTED)
            }
        }
        Shizuku.addRequestPermissionResultListener(listener)
        Shizuku.requestPermission(REQ_CODE)
        cont.invokeOnCancellation { Shizuku.removeRequestPermissionResultListener(listener) }
    }

    /**
     * Run a shell command under the `shell` UID via Shizuku's privileged
     * process. Returns merged stdout+stderr.
     */
    fun shellExec(command: String, timeoutMs: Long = 30_000L): String {
        require(isGranted()) { "Shizuku permission not granted" }
        val proc = Shizuku.newProcess(arrayOf("sh", "-c", command), null, null)
        val out = StringBuilder()
        val deadline = System.currentTimeMillis() + timeoutMs
        proc.inputStream.bufferedReader().use { reader ->
            while (System.currentTimeMillis() < deadline) {
                val line = reader.readLine() ?: break
                out.append(line).append('\n')
            }
        }
        if (proc.isAlive) {
            proc.destroy()
            out.append("\n[hermes: command exceeded ${timeoutMs}ms timeout]")
        }
        return out.toString()
    }
}
