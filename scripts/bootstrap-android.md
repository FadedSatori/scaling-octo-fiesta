# S24 bootstrap (Android — sideload + first-run wizard)

Android can't be provisioned from a desktop script without ADB, so the S24
flow is: build (or download) the Hermes APK, sideload it, and let the in-app
wizard handle Tailscale, Shizuku, model download, and mesh registration.

## 1. Get the APK

Either:
- Download the latest signed APK from the GitHub Releases page of this repo, or
- Build locally — see [`../android/README.md`](../android/README.md).

## 2. Sideload

1. Transfer the APK to the S24 (USB, Quick Share, or browser download).
2. Open it with Files; allow "Install unknown apps" from your file manager.
3. Install. Open Hermes.

## 3. First-run wizard (handled in-app)

The wizard walks the user through:

1. **Tailscale**
   - Opens Play Store to install Tailscale if missing.
   - Prompts user to sign in and tag the device with hostname `s24.hermes-net`.

2. **Shizuku** (the privilege layer for filesystem + desktop tools)
   - Opens Play Store to install [Shizuku](https://shizuku.rikka.app/).
   - Walks through wireless ADB pairing on Android 11+ (no PC needed):
     - Settings → Developer options → Wireless debugging → Pair device with
       pairing code.
     - Shizuku app → Pairing → enter code.
     - Tap "Start" in Shizuku to launch the privileged service.
   - Hermes requests Shizuku permission; user approves once.

3. **Battery optimization**
   - Opens Settings → Apps → Hermes → Battery → "Unrestricted".
   - Required so Samsung's One UI doesn't kill the foreground service.

4. **Model download**
   - Verifies the bundled Qwen2.5-Coder 3B Q4f16_1 weights unpacked correctly.
   - Optionally downloads Hermes-3-3B-MLC for offline tool-calling.

5. **Mesh registration**
   - Connects to the laptops over Tailscale (`g14.hermes-net:4222` for NATS).
   - Subscribes to `hermes.req.s24` and registers in the device directory.

6. **Smoke test**
   - Runs the installer agent end-to-end: lists `/sdcard/Download`, captures
     a screenshot, writes a test file. Reports pass/fail.

## 4. Verifying

- Notification drawer should show a persistent "Hermes is running" entry.
- From a laptop on the same Tailnet:
  ```powershell
  curl http://s24.hermes-net:8765/healthz
  ```
- Conversation history should appear under Settings → Sessions.

## Troubleshooting

- **Shizuku stops after reboot** — Wireless ADB requires re-pairing after a
  reboot on most builds. Either keep the phone plugged in (USB ADB persists)
  or use the Shizuku tile in Quick Settings to restart it.
- **Foreground service killed** — Re-check battery optimization. On One UI
  also disable "Put unused apps to sleep" for Hermes.
- **No GPU acceleration** — MLC needs Adreno OpenCL drivers. S24 has these
  out of the box; if you see CPU fallback in logs, file an issue with the
  device's `chrome://gpu` equivalent (`adb shell dumpsys SurfaceFlinger`).
