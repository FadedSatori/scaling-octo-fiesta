# Propagation across the mesh

Once a device is bootstrapped, configuration changes flow to the others
through git + a NATS event.

## How it works

1. You edit something under `configs/` or a prompt file, on any device.
2. Run `scripts/propagate.ps1`. It commits + pushes the diff, then
   publishes `hermes.events.config_changed` on NATS.
3. Each other device's daemon is subscribed to that subject. On message,
   it does:
   - `git pull --ff-only` in the local repo clone
   - revalidates `daemon.yml` against `DaemonConfig`
   - hot-reloads the affected MCP servers (or kicks NSSM to restart if a
     restart is required)

## Model promotion

A separate path for new model versions:

1. On the G14 (the strongest GPU), `ollama pull <new-tag>`.
2. Run `python -m hermes.eval --model <new-tag>` (planned in v0.2) which
   scores against a pinned set of tasks.
3. If the score beats the current incumbent by ≥ 2%, publish
   `hermes.events.model_promoted` with the new tag.
4. Lenovo's daemon receives the event, pulls the new tag (sized
   appropriately for its VRAM), and updates its config.
5. The phone never auto-upgrades models; the user picks new weights from
   the in-app model browser.

## Smoke after a propagate

```powershell
# from any device:
$nats = "nats://UNIT-G14-MainNode:4222"
nats request hermes.req.lenovo `
    '{"prompt": "echo hermes-prop-test via shell", "max_steps": 2}' --raw

nats request hermes.req.s24 `
    '{"prompt": "list /sdcard/Download", "max_steps": 2}' --raw
```

If both return final answers, the propagate worked.
