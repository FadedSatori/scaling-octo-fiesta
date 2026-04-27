package ai.mlc.mlcchat.hermes.inference

import android.content.Context
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.io.File

/**
 * Per-device runtime config. Persisted as JSON under filesDir so the
 * first-run wizard can edit it without rebuilding. Defaults are the
 * v0.1 single-device S24 setup with Qwen2.5-Coder 3B.
 */
@Serializable
data class HermesConfig(
    val device: String = "s24",
    val modelId: String = DEFAULT_MODEL_ID,
    val modelLib: String = DEFAULT_MODEL_LIB,
    /** Path under filesDir/models/<modelId> where MLC unpacked the bundle. */
    val modelDir: String = "models/$DEFAULT_MODEL_ID",
    /** Tailnet URL of the preferred laptop daemon. Empty = local-only. */
    val remoteUrl: String = "",
    /** Prefer remote when context > this many chars. 0 = always local. */
    val remoteContextThreshold: Int = 0,
) {
    fun modelAbsolutePath(ctx: Context): File = File(ctx.filesDir, modelDir)

    companion object {
        const val DEFAULT_MODEL_ID = "Qwen2.5-Coder-3B-Instruct-q4f16_1-MLC"
        const val DEFAULT_MODEL_LIB = "qwen2_q4f16_1"

        private const val FILE_NAME = "hermes-config.json"
        private val json = Json { prettyPrint = true; ignoreUnknownKeys = true }

        fun load(ctx: Context): HermesConfig {
            val f = File(ctx.filesDir, FILE_NAME)
            if (!f.exists()) return HermesConfig()
            return runCatching { json.decodeFromString<HermesConfig>(f.readText()) }
                .getOrElse { HermesConfig() }
        }

        fun save(ctx: Context, cfg: HermesConfig) {
            File(ctx.filesDir, FILE_NAME).writeText(json.encodeToString(serializer(), cfg))
        }
    }
}
