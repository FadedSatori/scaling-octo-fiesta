package ai.mlc.mlcchat.hermes.mcp

import ai.mlc.mlcchat.hermes.shizuku.ShizukuClient
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.File

interface ToolNamespace {
    val name: String
    val ops: List<String>
    suspend fun call(op: String, args: JsonObject): String
}

class ToolRegistry(private val namespaces: Map<String, ToolNamespace>) {
    fun get(ns: String): ToolNamespace? = namespaces[ns]
    fun manifest(): String = buildString {
        appendLine("Tools:")
        for ((ns, t) in namespaces) appendLine("  $ns: ${t.ops.joinToString(", ")}")
    }
}

/* ------------------------------ fs.* ------------------------------ */

class FsTool(private val roots: List<File>) : ToolNamespace {
    override val name = "fs"
    override val ops = listOf("read", "write", "list")

    private fun resolve(p: String): File {
        val candidate = File(p).canonicalFile
        require(roots.any { candidate.absolutePath.startsWith(it.absolutePath) }) {
            "path '$p' is outside allowed roots"
        }
        return candidate
    }

    override suspend fun call(op: String, args: JsonObject): String = when (op) {
        "read" -> {
            val path = args.string("path")
            resolve(path).readText().take(args.int("max_bytes", 256_000))
        }
        "write" -> {
            val path = args.string("path")
            val content = args.string("content")
            val f = resolve(path)
            f.parentFile?.mkdirs()
            f.writeText(content)
            "wrote ${content.length} chars to ${f.absolutePath}"
        }
        "list" -> {
            val path = args.string("path")
            resolve(path).listFiles()?.sortedBy { it.name }?.joinToString("\n") {
                (if (it.isDirectory) "d " else "f ") + it.name
            } ?: ""
        }
        else -> "error: unknown op '$op'"
    }
}

/* --------------------------- shell.exec --------------------------- */

class ShellTool : ToolNamespace {
    override val name = "shell"
    override val ops = listOf("exec")
    override suspend fun call(op: String, args: JsonObject): String {
        if (op != "exec") return "error: unknown op '$op'"
        val cmd = args.string("command")
        val timeoutMs = args.long("timeout_seconds", 30) * 1000L
        return ShizukuClient.shellExec(cmd, timeoutMs)
    }
}

/* ----------------------------- ui.* ------------------------------- */

class UiTool : ToolNamespace {
    override val name = "ui"
    override val ops = listOf("dump", "tap", "swipe", "input_text")
    override suspend fun call(op: String, args: JsonObject): String {
        // All ops are implemented by shelling out via Shizuku's `shell` UID.
        // This avoids pulling in a UiAutomator dep and keeps the surface narrow.
        val cmd = when (op) {
            // /dev/tty requires a controlling TTY (works only from `adb shell`).
            // Shizuku spawns `sh -c` with no TTY, so dump to /data/local/tmp/
            // (writable by the shell UID) then cat the XML back.
            "dump" -> "uiautomator dump /data/local/tmp/hermes-ui.xml >/dev/null 2>&1 && cat /data/local/tmp/hermes-ui.xml"
            "tap" -> "input tap ${args.int("x")} ${args.int("y")}"
            "swipe" -> "input swipe ${args.int("x1")} ${args.int("y1")} ${args.int("x2")} ${args.int("y2")} ${args.int("duration_ms", 300)}"
            "input_text" -> "input text ${args.string("text").shellEscape()}"
            else -> return "error: unknown op '$op'"
        }
        return ShizukuClient.shellExec(cmd)
    }

    private fun String.shellEscape(): String =
        "'" + replace("'", "'\\''").replace(" ", "%s") + "'"
}

/* --------------------------- app.launch --------------------------- */

class AppTool : ToolNamespace {
    override val name = "app"
    override val ops = listOf("launch", "kill")
    override suspend fun call(op: String, args: JsonObject): String = when (op) {
        "launch" -> ShizukuClient.shellExec("monkey -p ${args.string("package")} -c android.intent.category.LAUNCHER 1")
        "kill" -> ShizukuClient.shellExec("am force-stop ${args.string("package")}")
        else -> "error: unknown op '$op'"
    }
}

/* ------------------------- JsonObject helpers --------------------- */

private fun JsonObject.string(key: String): String =
    requireNotNull(this[key]?.jsonPrimitive?.content) { "missing arg: $key" }

private fun JsonObject.int(key: String, default: Int? = null): Int =
    this[key]?.jsonPrimitive?.content?.toIntOrNull()
        ?: default
        ?: error("missing arg: $key")

private fun JsonObject.long(key: String, default: Long): Long =
    this[key]?.jsonPrimitive?.content?.toLongOrNull() ?: default
