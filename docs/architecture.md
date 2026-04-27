# Hermes architecture

## Goals

- A self-hosted Claude-Code-style agent stack across an S24 phone, a Lenovo
  laptop, and an ASUS ROG Zephyrus G14.
- Agents on any device can dispatch work to the others.
- Local-first: every device can run a useful agent loop offline.
- No cloud LLM dependencies; built around Nous Research's Hermes models with
  Hermes-2-Pro JSON tool-call format.

## Topology

```
                       Tailscale mesh (WireGuard)
   ┌────────────────────────────────────────────────────────┐
   │                                                        │
┌──┴──────────┐         ┌──────────────┐         ┌──────────┴──┐
│  S24 phone  │◀──MCP──▶│  G14 (Win11) │◀──MCP──▶│ Lenovo (Win)│
│             │         │              │         │             │
│ MLC LLM     │         │ Ollama       │         │ Ollama      │
│ Qwen 3B     │         │ Hermes3:8B   │         │ Hermes3:8B  │
│ Shizuku     │         │ Coder 32B    │         │ Coder 14B   │
│ FGS+Ktor    │         │ NATS+Qdrant  │         │             │
│ port 8765   │         │ ports 4222/  │         │ daemon      │
│             │         │   6333/8765  │         │ port 8765   │
└─────────────┘         └──────────────┘         └─────────────┘
```

## Layers

### Mesh — Tailscale
- Free tier, 100-device limit, MagicDNS.
- Stable hostnames: `s24.hermes-net`, `g14.hermes-net`, `lenovo.hermes-net`.
- ACL pinned to the four Hermes ports (see `configs/tailscale-acl.example.json`).
- Wake-on-LAN configured on the laptops; phone can wake them through the
  Tailscale subnet router.

### Per-device runtime

**Windows laptops**
- Inference: Ollama (`hermes3:8b` for tool-calling, `qwen2.5-coder:*` sized to
  detected VRAM at install time).
- Daemon: Python 3.12 FastAPI app under NSSM as service `Hermes`. See
  `hermes/daemon/__main__.py`.
- MCP servers: `fs` (sandboxed), `shell` (PowerShell), `inference`. Mounted
  under `/mcp/<name>/` on the daemon's port 8765.

**S24**
- Forked MLC Chat app — see `android/`.
- Foreground service hosts a Ktor HTTP server matching the laptop's MCP API.
- Tools backed by Shizuku (ADB-level permissions, no root): `fs`, `shell`,
  `ui`, `app`.

### Dispatch — NATS JetStream
- Single instance on the G14. Subjects:
  - `hermes.req.<device>` — request inbox per device
  - `hermes.resp.<id>` — replies (NATS request/reply)
  - `hermes.events.*` — config changes, model promotions, audit logs
- Streams give durable conversation history + tool-call audit log without a
  separate database.

### Shared state — Qdrant
- Docker on G14, exposed on Tailscale only (`6333`).
- Collections per project. Embeddings via `nomic-embed-text` on Ollama.

### Background execution
- Windows: NSSM service auto-start.
- Android: `START_STICKY` foreground service + `BootReceiver` on
  `BOOT_COMPLETED`. Battery-opt opt-out is required on Samsung One UI.

## Routing rules

- Phone agent runs locally for: short prompts, offline tasks, anything with
  hard latency requirements (under ~3s round-trip).
- Phone dispatches to G14 (preferred) / Lenovo (fallback) for: long-form
  code synthesis, multi-file refactors, anything needing the larger
  Qwen2.5-Coder.
- A simple heuristic ships in v0.2: if estimated context > 1.5k tokens,
  dispatch.

## Security boundaries

- Tailscale is the network trust boundary. Nothing on these ports is exposed
  to the public internet.
- The filesystem MCP server is the only sandboxed component — explicit
  allowlist of root directories.
- The shell MCP server is unsandboxed by design. The agent prompt and the
  Tailscale ACL are the authorization boundary, not the code.
- Shizuku permission is granted once; revoked by uninstalling Shizuku or
  rebooting the phone (wireless ADB doesn't survive reboots).

## What v0.1 delivers vs v0.2

- **v0.1**: Single-device S24 agent. Local Qwen2.5-Coder 3B + Shizuku tools.
  No mesh, no laptop daemons.
- **v0.2**: Laptop daemons via `bootstrap-windows.ps1`, Tailscale wiring,
  NATS dispatch, propagation script.
