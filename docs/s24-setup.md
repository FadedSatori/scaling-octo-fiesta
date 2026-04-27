# S24 setup

The phone is the v0.1 deliverable. End-user steps are in
[`../scripts/bootstrap-android.md`](../scripts/bootstrap-android.md). This doc
is the developer view.

## Architecture recap

```
┌────────────────────────────────────────────────────┐
│ Hermes Android app (forked from MLC Chat)          │
│                                                    │
│  HermesActivity (launcher) ─ Compose: wizard+chat  │
│      │                                             │
│      │ POST /agent/run        ▲ on app open        │
│      ▼                        │ startForegroundSvc │
│  ┌──────────────┐    ┌─────────┴─────────────────┐ │
│  │ MLC LLM      │    │ HermesForegroundService   │ │
│  │ Qwen2.5-Coder│◀──▶│ Ktor on 127.0.0.1:8765    │ │
│  │ 3B Q4f16_1   │    │ /healthz, /agent/run      │ │
│  └──────────────┘    └────────────┬──────────────┘ │
│         ▲                         │                │
│         │ MlcChatBackend          ▼                │
│  ┌──────┴───────────────────────────────────────┐  │
│  │ HermesAgentLoop (tool-call loop)             │  │
│  └──────────────┬───────────────────────────────┘  │
│                 │                                  │
│                 ▼                                  │
│  ┌──────────────────────────────────────────────┐  │
│  │ ToolRegistry: fs, shell, ui, app             │  │
│  │     │                                        │  │
│  │     └─▶ ShizukuClient ─ shell user privileges│  │
│  └──────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────┘
```

## Build

```bash
cd android
./apply-overlay.sh                  # clones MLC Chat at the pinned commit and merges overlay
cd mlc-chat/android/MLCChat
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

`apply-overlay.sh` is idempotent — re-running re-syncs sources but won't
re-clone. Pass `--rebuild` to also run `assembleDebug` at the end.

Requirements: JDK 17, Android SDK + NDK (MLC's native libs), Python 3
(used by the manifest/gradle patcher).

## Why MLC Chat as base

- TVM-compiled models on Adreno via OpenCL/Vulkan — closest thing to "real"
  GPU inference on Android. llama.cpp on phone is CPU-bound and slower.
- Existing chat UI we can graft tool-call rendering onto.
- Apache-licensed.

## Why Shizuku, not root

- No Knox trip → Samsung Pay, banking apps, work profile keep working.
- One-time setup via wireless ADB pairing on Android 11+ — no PC required.
- Shizuku runs as the `shell` user, which gives us:
  - `am start` / `am force-stop`
  - `input tap/swipe/text`
  - `uiautomator dump`
  - Most of `/sdcard` directly without SAF prompts
  - Reading `/data/data/<other-app>` in many cases (depends on SELinux policy)
- We'd lose `/data/data` write to other apps, kernel-mode hooks, and
  persistent root daemons. Acceptable for v0.1.

## Inference bridge

Wired up via:

- `inference/ChatBackend.kt` — interface (`isAvailable`, `chat`).
- `inference/MlcChatBackend.kt` — wraps `ai.mlc.mlcllm.MLCEngine`. Loads
  the model lazily under a mutex (one-time reload), then streams completion
  chunks and concatenates them so the parser sees a complete response.
- `inference/RemoteChatBackend.kt` — POSTs to a laptop daemon's
  `/mcp/inference/chat` over Tailscale. Inactive in v0.1 (empty
  `remoteUrl`).
- `inference/InferenceProvider.kt` — picks an order (remote-first when
  context exceeds threshold and configured, otherwise local-first), falls
  through on failure.
- `inference/HermesConfig.kt` — JSON config persisted under filesDir.
  Defaults to `Qwen2.5-Coder-3B-Instruct-q4f16_1-MLC` with model lib
  `qwen2_q4f16_1`. The first-run wizard's "Verify model" step writes
  the unpacked path here.

`HermesForegroundService` constructs an `InferenceProvider` from the
loaded config and passes `provider::chat` as the agent's `infer` lambda.
No more stub.

If the MLC SDK API shifts in a future upstream pin, `MlcChatBackend` is
the only file to update (the `asText()` adapter at the bottom isolates
the delta-content shape).

## Tool-call rendering in the chat UI

Each `<tool_call>` / `<tool_response>` pair is collapsed into a single
expandable card in the chat surface. The base MLC Chat layout is forked
into a Hermes-aware Composable that detects these tags and renders them
distinctly from plain assistant text.

## Smoke prompts

These are the agent invocations to test post-install:

```
list /sdcard/Download
open Chrome
write 'hello hermes' to /sdcard/hermes-test.txt
take a screenshot and tell me what's visible
```

The first three should work with v0.1; the fourth requires vision and is
deferred to a later release.
