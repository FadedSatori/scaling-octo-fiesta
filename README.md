# Hermes

Local-first, Claude-Code-style agent stack across an S24 phone, a Lenovo laptop,
and an ASUS G14 — all on Windows except the phone. Built around Nous Research's
Hermes models with the Hermes-2-Pro JSON tool-call format.

## What this is

A self-hosted alternative to Claude Code:

- A **Python daemon** (`hermes/`) that runs on each Windows laptop as an NSSM
  service, hosting MCP servers (filesystem, shell, web, inference) and an
  Ollama-backed inference layer.
- An **Android app** (`android/`, forked from MLC Chat) that runs Qwen2.5-Coder
  3B locally on the phone's Adreno 750 GPU, exposes the same MCP tool surface
  via a foreground service, and uses Shizuku for ADB-level filesystem and
  desktop-control privileges (no root required).
- A **Tailscale mesh** that ties all three devices together so agents on any
  one can dispatch to the others over WireGuard.
- **NATS JetStream** + **Qdrant** on the G14 for cross-device dispatch and
  shared vector memory.

## Bootstrap

**Windows (Lenovo / G14)**
```powershell
irm https://raw.githubusercontent.com/<you>/scaling-octo-fiesta/main/scripts/bootstrap-windows.ps1 | iex
```

**S24** — see [`scripts/bootstrap-android.md`](scripts/bootstrap-android.md).
The APK is sideloaded; the in-app first-run wizard handles Tailscale, Shizuku
pairing, model download, and mesh registration.

## Layout

```
hermes/      Python daemon for the Windows laptops
android/     Overlay sources to apply on top of an MLC Chat Android fork
scripts/     Bootstrap + propagation scripts
configs/     Per-device YAML, NATS/Tailscale templates
docs/        Architecture and per-device setup guides
```

## Status

v0.1 in progress — single-device S24 agent with local Qwen2.5-Coder 3B and
Shizuku-backed MCP tools. Mesh + laptop daemons land in v0.2.

See [`docs/architecture.md`](docs/architecture.md) for the full design.
