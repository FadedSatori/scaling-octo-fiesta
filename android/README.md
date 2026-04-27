# Hermes Android (S24 app)

The S24 client is a fork of [MLC Chat Android](https://github.com/mlc-ai/mlc-llm/tree/main/android/MLCChat)
with a Hermes overlay that adds:

- A **launcher activity** (`HermesActivity`) showing a setup wizard +
  chat surface. MLC Chat's existing UI stays accessible for model
  management.
- A **foreground service** hosting a Ktor HTTP server on `127.0.0.1:8765`.
- **Shizuku-backed tools** for filesystem, shell, UI automation, and
  app launches — ADB-level privileges with no root.
- A **Hermes-2-Pro tool-call agent loop** that drives the bundled
  Qwen2.5-Coder 3B (Q4f16_1) model.
- An **MLC inference bridge** (`MlcChatBackend`) plus a **remote chat
  backend** stub for v0.2 mesh dispatch.

This directory contains only the overlay — the MLC Chat fork is cloned
alongside it at build time by `apply-overlay.sh`.

## Build (one-liner)

```bash
cd android
./apply-overlay.sh                  # clone MLC Chat + apply overlay
cd mlc-chat/android/MLCChat
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

`./apply-overlay.sh --rebuild` also runs `gradle assembleDebug` after
applying.

Requirements: JDK 17, Android SDK + NDK (MLC's native libs), Python 3
(used by the manifest/gradle patcher).

## Bundled model

The default config points at `Qwen2.5-Coder-3B-Instruct-q4f16_1-MLC` with
model lib `qwen2_q4f16_1`. MLC Chat's existing model-manager flow handles
download + unpacking under `filesDir/models/`. The wizard's "Verify
model" step confirms the directory exists.

## Layout (overlay only)

```
overlay/
  app/
    src/main/
      kotlin/ai/mlc/mlcchat/hermes/
        HermesActivity.kt                    launcher (Compose UI host)
        agent/HermesAgentLoop.kt             Hermes-2-Pro tool-call loop
        agent/HermesParser.kt                tool-call XML/JSON parser
        inference/ChatBackend.kt             pluggable interface
        inference/MlcChatBackend.kt          local MLC LLM
        inference/RemoteChatBackend.kt       Tailscale dispatch (v0.2)
        inference/InferenceProvider.kt       backend chooser
        inference/HermesConfig.kt            per-device JSON config
        mcp/Tools.kt                         fs / shell / ui / app tools
        service/HermesForegroundService.kt   FGS + Ktor HTTP server
        service/BootReceiver.kt              re-arm FGS after reboot
        shizuku/ShizukuClient.kt             permission + privileged exec
        ui/HermesScreen.kt                   wizard + chat Composable
        ui/HermesClient.kt                   in-process client → 8765
        ui/HermesPrefs.kt                    wizard-complete flag
        wizard/FirstRunWizard.kt             setup steps (data only)
      res/values/
        strings_hermes.xml
  MERGES.md                                  manifest + gradle deltas (manual)
apply-overlay.sh                             clone + auto-merge script
```

See [`../scripts/bootstrap-android.md`](../scripts/bootstrap-android.md)
for end-user sideload + first-run steps once the APK is built.
