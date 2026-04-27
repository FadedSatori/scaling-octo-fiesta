package ai.mlc.mlcchat.hermes.wizard

import ai.mlc.mlcchat.hermes.shizuku.ShizukuClient
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.core.content.ContextCompat

/**
 * First-run wizard steps. Each step is independently runnable so the UI
 * can render them as a checklist and let the user redo any of them.
 */
sealed interface WizardStep {
    val title: String
    val description: String
    fun isComplete(ctx: Context): Boolean
    fun start(ctx: Context)
}

object InstallTailscale : WizardStep {
    override val title = "Install Tailscale"
    override val description = "Joins this phone to the Hermes mesh."
    override fun isComplete(ctx: Context): Boolean = ctx.isPackageInstalled(TS_PKG)
    override fun start(ctx: Context) = ctx.openPlayStore(TS_PKG)
    private const val TS_PKG = "com.tailscale.ipn"
}

object InstallShizuku : WizardStep {
    override val title = "Install Shizuku"
    override val description = "Grants ADB-level privileges without root."
    override fun isComplete(ctx: Context): Boolean = ShizukuClient.isInstalled()
    override fun start(ctx: Context) = ctx.openPlayStore("moe.shizuku.privileged.api")
}

object GrantShizuku : WizardStep {
    override val title = "Grant Shizuku permission"
    override val description = "Hermes asks Shizuku once; tap Allow."
    override fun isComplete(ctx: Context): Boolean = ShizukuClient.isGranted()
    override fun start(ctx: Context) {
        // Permission request is async; UI layer should call ShizukuClient.request()
        // from a coroutine when this step is tapped.
    }
}

object DisableBatteryOpt : WizardStep {
    override val title = "Disable battery optimization"
    override val description = "Stops One UI from killing the foreground service."
    override fun isComplete(ctx: Context): Boolean {
        val pm = ctx.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
        return pm.isIgnoringBatteryOptimizations(ctx.packageName)
    }
    override fun start(ctx: Context) {
        val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            .setData(Uri.parse("package:${ctx.packageName}"))
        ContextCompat.startActivity(ctx, intent, null)
    }
}

object VerifyModel : WizardStep {
    override val title = "Verify Qwen2.5-Coder 3B"
    override val description = "Checks the bundled MLC weights unpacked correctly."
    override fun isComplete(ctx: Context): Boolean {
        val dir = java.io.File(ctx.filesDir, "models/qwen2.5-coder-3b-q4f16_1")
        return dir.exists() && (dir.listFiles()?.isNotEmpty() ?: false)
    }
    override fun start(ctx: Context) { /* triggered by MLC's own model manager */ }
}

val WIZARD_STEPS: List<WizardStep> = listOf(
    InstallTailscale, InstallShizuku, GrantShizuku, DisableBatteryOpt, VerifyModel,
)

private fun Context.isPackageInstalled(pkg: String): Boolean = try {
    packageManager.getPackageInfo(pkg, 0); true
} catch (_: Exception) { false }

private fun Context.openPlayStore(pkg: String) {
    val market = Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=$pkg"))
        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    try { startActivity(market) } catch (_: Exception) {
        startActivity(Intent(Intent.ACTION_VIEW,
            Uri.parse("https://play.google.com/store/apps/details?id=$pkg"))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}
