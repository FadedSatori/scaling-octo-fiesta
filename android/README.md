# Hermes Android (S24 app)

The S24 client is a fork of [MLC Chat Android](https://github.com/mlc-ai/mlc-llm/tree/main/android/MLCChat)
with a Hermes overlay that adds:

- A **foreground service** hosting a Ktor HTTP server on `127.0.0.1:8765` that
  speaks the same MCP-style endpoints as the laptop daemon.
- **Shizuku-backed tools** for filesystem, shell, UI automation, and screen
  capture — ADB-level privileges with no root.
- A **Hermes-2-Pro tool-call agent loop** that drives the bundled
  Qwen2.5-Coder 3B (Q4f16_1) model.
- A **first-run wizard** for Tailscale + Shizuku setup, battery-opt opt-out,
  model verification, and mesh registration.

This directory contains only the overlay — the MLC Chat fork itself is
cloned alongside it at build time.

## Build

```bash
# 1) Clone MLC Chat as the app base
cd android
git clone --depth 1 https://github.com/mlc-ai/mlc-llm.git mlc-chat
cp -R overlay/* mlc-chat/android/MLCChat/

# 2) Apply the manifest + gradle merges (see overlay/MERGES.md for diffs)
#    or run the helper script (Linux/macOS):
./apply-overlay.sh

# 3) Build
cd mlc-chat/android/MLCChat
./gradlew assembleRelease
# APK at: app/build/outputs/apk/release/app-release.apk
```

## Bundled model

Qwen2.5-Coder 3B Q4f16_1 (~2GB) is fetched at build time via MLC's standard
`prepare_libs.sh` flow. See MLC docs for cross-compilation instructions if
you want to swap in a different quantization.

## Layout (overlay only)

```
overlay/
  app/
    src/main/
      kotlin/ai/mlc/mlcchat/hermes/
        service/HermesForegroundService.kt   FGS + Ktor HTTP server
        shizuku/ShizukuClient.kt             permission + privileged exec
        agent/HermesAgentLoop.kt             tool-call loop
        agent/HermesParser.kt                Hermes-2-Pro parser
        mcp/Tools.kt                         fs / shell / ui / screen tools
        wizard/FirstRunWizard.kt             setup flow
      res/values/
        strings_hermes.xml
  MERGES.md                                  AndroidManifest.xml + build.gradle deltas
```

See [`../scripts/bootstrap-android.md`](../scripts/bootstrap-android.md) for
end-user sideload + first-run steps.
