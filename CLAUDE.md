# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this codebase is

**Hermes** is a self-hosted, local-first alternative to Claude Code that
runs across three of the author's devices: a Samsung S24 (Android) and two
Windows 11 laptops (a Lenovo and an ASUS G14). All three speak the same
HTTP wire protocol and Hermes-2-Pro JSON tool-call format. Agents on any
device can dispatch work to the others over a Tailscale mesh.

The phone runs Qwen2.5-Coder 3B locally via MLC LLM (GPU-accelerated on
the Adreno 750). The laptops run larger models (Hermes-3 8B for tool
calling, Qwen2.5-Coder up to 32B for code) via Ollama. NATS JetStream
on the G14 handles cross-device request/reply and config propagation
events. Qdrant is installed by the bootstrap on the G14 for shared vector
memory, but no daemon code talks to it yet — it's reserved for v0.2.

All work lives on the `claude/add-claude-documentation-kk7wT` branch.
`main` is empty; don't try to bootstrap from it.

See `README.md` for the user-facing overview and `docs/architecture.md`
for the full design.

## Commands

### Python daemon (`hermes/`)

```bash
# install (editable) — assumes Python 3.12
pip install -e "hermes/[dev]"

# run the daemon
python -m hermes.daemon --config /path/to/daemon.yml

# run the post-bootstrap installer agent (smoke tests + mesh registration)
python -m hermes.daemon.installer --config /path/to/daemon.yml --device g14

# evaluation harness (smoke prompts against a running daemon)
python -m hermes.eval

# publish a propagation event manually
python -m hermes.routing publish --nats nats://g14.hermes-net:4222 \
    --subject hermes.events.config_changed --payload '{"by":"manual"}'

# tests
cd hermes && python -m pytest tests/ -q --tb=short
cd hermes && python -m pytest tests/test_parser.py::TestParse::test_single_tool_call
```

`pyproject.toml` sets `asyncio_mode = "auto"` and `pythonpath = [".."]`,
so tests must be invoked from inside `hermes/` (not the repo root).

### Android app (`android/`)

```bash
# 1. clone MLC Chat at the pinned SHA + copy overlay sources + patch manifest/gradle
cd android
./apply-overlay.sh             # idempotent; safe to re-run
./apply-overlay.sh --rebuild   # also runs assembleDebug at the end

# 2. build
cd mlc-chat/android/MLCChat
./gradlew assembleDebug

# 3. install on the S24
adb install -r app/build/outputs/apk/debug/app-debug.apk

# JVM unit tests (no emulator — HermesParser and HermesAgentLoop are pure JVM)
cd mlc-chat/android/MLCChat
./gradlew test
```

Requirements: JDK 17, Android SDK + NDK (MLC native libs), Python 3 (the
manifest/gradle patcher inside `apply-overlay.sh` is Python).

### Laptop bootstrap (Lenovo / G14, Windows 11)

```powershell
# elevated PowerShell:
irm https://raw.githubusercontent.com/fadedsatori/scaling-octo-fiesta/main/scripts/bootstrap-windows.ps1 | iex
```

Installs Tailscale, Ollama, Python 3.12, Git, NSSM (and on G14:
NATS-server + Docker Desktop for Qdrant), clones this repo, creates a
venv, pulls VRAM-appropriate Ollama models, registers `Hermes` NSSM
service, hands off to `hermes.daemon.installer`.

Other scripts:
- `scripts/install-models.ps1` — standalone VRAM-aware Ollama puller.
- `scripts/propagate.ps1` — commits configs + publishes
  `hermes.events.config_changed` on NATS so other devices `git pull` and
  reload.

### CI

- `.github/workflows/android-apk.yml` — applies overlay, builds debug APK,
  uploads artifact, runs JVM tests. Steps gated on overlay-clone success
  via `continue-on-error` + `if:` checks.
- `.github/workflows/python-tests.yml` — `pytest` on push/PR touching
  `hermes/**`.

## Architecture — the big picture

### Three independent runtimes, one wire protocol

| | Python (laptops, NSSM service) | Kotlin (phone, Foreground Service) |
| --- | --- | --- |
| HTTP server | uvicorn / FastAPI on `:8765` | Ktor CIO on `127.0.0.1:8765` |
| Endpoints | `GET /healthz`, `POST /agent/run`, `/mcp/<ns>/...` | `GET /healthz`, `POST /agent/run` |
| Parser | `hermes/agent/parser.py` | `android/.../agent/HermesParser.kt` |
| Agent loop | `hermes/agent/loop.py` | `android/.../agent/HermesAgentLoop.kt` |
| Inference | `mcp_servers/inference.py` (Ollama, HTTP endpoint, not an agent tool) | `inference/MlcChatBackend.kt` (MLCEngine) |
| Tool namespaces (agent-callable) | `fs`, `shell` | `fs`, `shell`, `ui`, `app` |
| Service mgmt | NSSM service `Hermes` | `HermesForegroundService` + `BootReceiver` |

**The parser + loop are hand-mirrored across Python and Kotlin. Any
change to one must be reflected in the other.** Both implement the same
Hermes-2-Pro tags:

```
<tool_call>{"name":"<ns>.<op>","arguments":{...}}</tool_call>
<tool_response>{"name":..., "content":...}</tool_response>
<final>...</final>   ← or implicit final when no tool call is present
```

Tool name format is strictly `<namespace>.<op>` (split on first `.`).

### Cross-device topology

```
        Tailscale mesh (WireGuard)
   s24.hermes-net ─┬─ g14.hermes-net ─┬─ lenovo.hermes-net
                   │                  │
                   ▼                  ▼
            NATS JetStream :4222 (G14)
              hermes.req.<device>     ← per-device inbox
              hermes.resp.<id>        ← NATS request/reply
              hermes.events.*         ← config_changed, model_promoted
            Qdrant :6333 (G14)        ← installed, no code integration yet
```

- Tailscale ACL (`configs/tailscale-acl.example.json`) is the network
  trust boundary. Daemon ports are not directly internet-exposed.
- Each daemon subscribes to `hermes.req.<device>` and replies via NATS
  request/reply. `routing.NatsRouter._on_request` runs the local
  `AgentLoop` and returns the result.
- `hermes.events.config_changed` triggers `routing.NatsRouter._on_config_changed`
  on each device: `git pull --ff-only`, re-validate `daemon.yml`, restart
  the NSSM service if the config diff matters.

### Android overlay pattern

`android/` is **not** a buildable Android project on its own. It contains
overlay sources that get applied on top of an MLC Chat fork at build
time. `android/apply-overlay.sh`:

1. Clones `mlc-ai/mlc-llm` at a 40-char SHA (`MLC_PIN` in the script —
   bump only after verifying a working build).
2. Copies `overlay/app/src/main/kotlin/.../hermes/*` into the MLC Chat
   `app/src/main/kotlin/` tree.
3. Patches `AndroidManifest.xml` programmatically (Python regex):
   strips MLC's `MAIN`/`LAUNCHER` intent-filter from MLC Chat's
   MainActivity, registers `HermesActivity` as the new launcher, adds
   the Foreground Service, BootReceiver, ShizukuProvider, permissions,
   and `<queries>`.
4. Patches `app/build.gradle.kts`: injects Shizuku, Ktor server (CIO,
   not Netty — Netty pulls JVM-only deps), Ktor client, kotlinx.serialization,
   Compose Material3, mlc4j project dep. Raises `minSdk = 30` (required
   by Shizuku's wireless ADB pairing).
5. Adds Kotlin test source roots.

The script is idempotent (guards on grep for inserted markers). If MLC
upstream renames an anchor, the regex patcher fails loudly — pin to a
known-good SHA before relying on reproducibility.

### Inference bridge (S24)

`InferenceProvider` picks per-call between `MlcChatBackend` (local) and
`RemoteChatBackend` (dispatch to a laptop over Tailscale). The choice is
governed by `HermesConfig.remoteUrl` (configured via the in-app
`ConfigureRemote` wizard step) and `remoteContextThreshold` (in
characters). MLC LLM's stream-delta content shape varies by SDK version —
`MlcChatBackend.asText()` is the single isolation point for that drift.

### Privilege model (S24)

Shizuku grants ADB-level privileges without root. The user installs the
Shizuku app, pairs it via wireless ADB once (Android 11+, hence
`minSdk=30`), and grants Hermes the permission. `ShizukuClient.shellExec`
runs commands under the `shell` UID; all of `Tools.kt`'s shell/ui/app
operations route through it. **Shizuku permission does not survive a
reboot** unless USB ADB is enabled — documented in `docs/troubleshooting.md`.

### Configuration

- Laptops: `configs/daemon.example.yml` is rendered by
  `bootstrap-windows.ps1` with `{{device}}`, `{{coder_model}}`,
  `{{nats_host}}`, `{{username}}`, `{{repo_root}}` placeholders → written
  to `%LOCALAPPDATA%\Hermes\daemon.yml`. Validated via Pydantic
  `DaemonConfig`.
- Phone: `HermesConfig` is a JSON file at `filesDir/hermes-config.json`.
  Defaults to `Qwen2.5-Coder-3B-Instruct-q4f16_1-MLC`.

### Filesystem sandbox

`hermes/mcp_servers/fs.py` (Python) and `android/.../mcp/Tools.kt#FsTool`
(Kotlin) both restrict reads/writes to an allowlist of roots and resolve
through `realpath` (`Path.resolve` / `File.canonicalFile`) to defeat
symlink escapes. Python raises `HTTPException(403)`; Kotlin throws
`IllegalArgumentException`, which the agent loop catches and surfaces
to the model as an `error: ...` string. `shell.exec` is **unsandboxed
by design** — the prompt + the Tailscale ACL are the trust boundary,
not the code.

**Android storage gotcha**: the Kotlin `FsTool` uses direct `File` I/O
(not Shizuku) and its default roots are `Environment.getExternalStorageDirectory()`
and `filesDir`. `apply-overlay.sh` does *not* inject
`READ_EXTERNAL_STORAGE` / `MANAGE_EXTERNAL_STORAGE`, so reads against
`/sdcard/Download` will fail at runtime on Android 11+. App-private
`filesDir` works. To read arbitrary `/sdcard` paths, either widen the
manifest patcher or route fs ops through Shizuku.

## Conventions worth knowing

- **Python ↔ Kotlin parity.** Touching `hermes/agent/parser.py` or
  `loop.py` without updating their Kotlin twins (or vice versa) creates
  silent protocol drift. The two test suites should catch most regressions
  but the system prompts and tool-manifest formatting are not covered.
- **Tool name format is `<namespace>.<op>`.** Always. The parser splits
  on the first `.` and the dispatcher rejects anything else.
- **`bind_host: "0.0.0.0"`** in the laptop daemon binds to all
  interfaces — Tailscale ACL keeps it safe. Don't replace with a
  hardcoded IP; v0.2 may auto-detect the Tailscale interface.
- **MLC SDK is volatile.** When bumping `MLC_PIN`, expect compile breaks
  in `MlcChatBackend.kt`. Most often the fix is in `asText()` or the
  `ChatCompletionMessage(...)` constructor call.
- **`apply-overlay.sh` is idempotent**, but the upstream MLC Chat layout
  may shift across SHAs. The script checks for known anchors and bails
  with a clear error if they're missing.
- **Shizuku is required for `shell`, `ui`, `app` — but not for `fs`.**
  `FsTool` uses direct `File` I/O against its allowlist roots.
  `ShellTool`, `UiTool`, `AppTool` route through `ShizukuClient.shellExec`
  (commands run under the `shell` UID). If you add a new tool that
  needs anything outside the app's private dir or the user-granted
  storage roots, route it through Shizuku — don't pile permissions
  into the manifest.
- **NATS subjects are flat strings, not topic patterns.** Subscribers
  use exact-match for `hermes.req.<device>`.
