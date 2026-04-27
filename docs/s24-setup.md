# S24 setup

The phone is the v0.1 deliverable. End-user steps are in
[`../scripts/bootstrap-android.md`](../scripts/bootstrap-android.md). This doc
is the developer view.

## Architecture recap

```
┌────────────────────────────────────────────────────┐
│ Hermes Android app (forked from MLC Chat)          │
│                                                    │
│  ┌──────────────┐    ┌─────────────────────────┐   │
│  │ MLC LLM      │    │ HermesForegroundService │   │
│  │ Qwen2.5-Coder│◀──▶│  Ktor on 127.0.0.1:8765 │   │
│  │ 3B Q4f16_1   │    │  /healthz, /agent/run   │   │
│  └──────────────┘    └────────────┬────────────┘   │
│                                   │                │
│                                   ▼                │
│  ┌──────────────────────────────────────────────┐  │
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
git clone --depth 1 https://github.com/mlc-ai/mlc-llm.git mlc-chat
cp -R overlay/* mlc-chat/android/MLCChat/
# Apply manifest + gradle merges from overlay/MERGES.md
cd mlc-chat/android/MLCChat
./gradlew assembleRelease
```

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

Wiring MLC's `MLCEngine` into `HermesAgentLoop.infer` is left as the v0.1
TODO — see `service/HermesForegroundService.kt:stubInfer`. The MLC Chat
upstream code already exposes a Kotlin `MLCEngine.chat(messages)` that we
wrap.

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
