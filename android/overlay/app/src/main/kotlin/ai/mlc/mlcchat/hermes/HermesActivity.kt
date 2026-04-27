package ai.mlc.mlcchat.hermes

import ai.mlc.mlcchat.hermes.service.HermesForegroundService
import ai.mlc.mlcchat.hermes.ui.HermesClient
import ai.mlc.mlcchat.hermes.ui.HermesPrefs
import ai.mlc.mlcchat.hermes.ui.HermesScreen
import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.core.content.ContextCompat

/**
 * Launcher activity for Hermes. Replaces MLC Chat's MainActivity as the
 * default entry point (see overlay/MERGES.md). MLC Chat's existing UI
 * remains reachable as a separate activity for model management.
 */
class HermesActivity : ComponentActivity() {

    private val notifPermLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { /* ignore — FGS notification will still fire on older APIs */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        ensureNotificationPermission()
        startHermesService()

        val prefs = HermesPrefs(this)
        val client = HermesClient()
        setContent { HermesTheme { HermesScreen(prefs, client) } }
    }

    private fun ensureNotificationPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        val granted = ContextCompat.checkSelfPermission(
            this, Manifest.permission.POST_NOTIFICATIONS
        ) == PackageManager.PERMISSION_GRANTED
        if (!granted) notifPermLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
    }

    private fun startHermesService() {
        val intent = Intent(this, HermesForegroundService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
    }
}

@Composable
private fun HermesTheme(content: @Composable () -> Unit) {
    MaterialTheme { Surface { content() } }
}
