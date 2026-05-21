# Troubleshooting

## Windows daemon

**Service starts and immediately stops.** Look at
`%LOCALAPPDATA%\Hermes\logs\stderr.log`. Most common: invalid `daemon.yml`
(YAML parse error) or Ollama not running.

**`ImportError: nats`** — the venv didn't get its deps. Re-run
`pip install -e %LOCALAPPDATA%\Hermes\repo\hermes` from the venv.

**Tailscale shows the laptop as offline.** `tailscale up` again. On
Windows the Tailscale service can crash silently after sleep — restart
the "Tailscale" Windows service.

**Ollama OOMs on the coder model.** Re-run `scripts/install-models.ps1` —
it re-detects VRAM and pulls a smaller variant.

## S24 app

**Persistent notification disappears after a few hours.** Battery
optimization re-enabled itself (One UI does this on its own). Settings →
Apps → Hermes → Battery → Unrestricted, and toggle "Put unused apps to
sleep" off for Hermes.

**Shizuku shows "stopped" after reboot.** Wireless ADB on the S24 needs
re-pairing after every reboot on most builds. Either:
- keep the phone tethered to a PC with USB ADB enabled (persists), or
- use the Shizuku Quick Settings tile to restart it manually after each
  boot.

**Tool calls fail with "permission denied".** Shizuku permission was
revoked. Open Shizuku → Authorized apps → Hermes → Allow.

**MLC says "no GPU"** in the inference log. Adreno OpenCL drivers should
be present on stock S24. Check `adb shell dumpsys SurfaceFlinger | grep
GLES`. If you've installed a custom kernel/ROM the OpenCL libs may have
been stripped.

## Mesh

**`hermes.req.s24` requests time out.** Phone's foreground service was
killed. See the battery-opt note above. Verify with
`curl http://UNIT-S24-EdgeNode:8765/healthz` from a laptop.

**Propagate doesn't pick up on Lenovo.** Daemon is up but not subscribed.
Check `stdout.log` for "subscribed: hermes.req.lenovo". If missing, the
NATS connection failed — verify firewall isn't blocking 4222 from
Tailscale traffic.
