"""NATS JetStream router.

Each device subscribes to `hermes.req.<device>`. Incoming requests are run
through the local agent loop and the result is published as a reply. A
small CLI is exposed under `python -m hermes.routing publish ...` for
firing config-change events from the propagation script.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import nats

if TYPE_CHECKING:
    from hermes.agent.loop import AgentLoop
    from hermes.daemon.__main__ import DaemonConfig

log = logging.getLogger("hermes.routing")


class NatsRouter:
    def __init__(self, *, url: str, device: str, agent: "AgentLoop",
                 cfg: "DaemonConfig | None" = None) -> None:
        self.url = url
        self.device = device
        self.agent = agent
        self._cfg = cfg
        self._nc: nats.NATS | None = None

    async def connect(self) -> None:
        self._nc = await nats.connect(self.url, name=f"hermes-{self.device}")
        log.info("NATS connected: %s", self.url)

    async def serve(self) -> None:
        if self._nc is None:
            raise RuntimeError("call connect() first")
        subject = f"hermes.req.{self.device}"
        await self._nc.subscribe(subject, cb=self._on_request)
        log.info("subscribed: %s", subject)
        await self._nc.subscribe("hermes.events.config_changed", cb=self._on_config_changed)
        log.info("subscribed: hermes.events.config_changed")
        # Keep the coroutine alive
        while True:
            await asyncio.sleep(3600)

    async def _on_request(self, msg: nats.aio.msg.Msg) -> None:
        try:
            payload = json.loads(msg.data.decode())
        except json.JSONDecodeError:
            await msg.respond(b'{"error":"invalid json"}')
            return
        from hermes.agent.loop import RunRequest  # local import to avoid cycle
        req = RunRequest.model_validate(payload)
        resp = await self.agent.run(req)
        await msg.respond(resp.model_dump_json().encode())

    async def _on_config_changed(self, msg: nats.aio.msg.Msg) -> None:
        """
        Received when any device runs propagate.ps1. Actions:
          1. git pull --ff-only in the local repo clone
          2. Re-validate daemon.yml against DaemonConfig
          3. Restart the Windows service if the config changed
        """
        try:
            payload = json.loads(msg.data.decode()) if msg.data else {}
        except json.JSONDecodeError:
            payload = {}
        log.info("config_changed: by=%s msg=%r",
                 payload.get("by", "unknown"), payload.get("msg", ""))

        if self._cfg is None:
            log.warning("config_changed: no cfg reference; skipping")
            return

        repo = Path(self._cfg.repo_root)
        if not repo.exists():
            log.warning("config_changed: repo_root %s not found; skipping pull", repo)
            return

        # Step 1: git pull
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", str(repo), "pull", "--ff-only"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                log.error("config_changed: git pull failed (exit %d):\n%s",
                          result.returncode, result.stderr.strip())
                return
            log.info("config_changed: git pull ok:\n%s", result.stdout.strip())
        except subprocess.TimeoutExpired:
            log.error("config_changed: git pull timed out after 60s")
            return
        except Exception as exc:  # noqa: BLE001
            log.exception("config_changed: git pull raised: %s", exc)
            return

        # Step 2: re-validate daemon.yml (lives one level above the repo clone)
        cfg_path = repo.parent / "daemon.yml"
        if not cfg_path.exists():
            log.warning("config_changed: daemon.yml not found at %s; skipping", cfg_path)
            return
        try:
            from hermes.daemon.__main__ import load_config  # local import to avoid cycle
            new_cfg = load_config(cfg_path)
            log.info("config_changed: daemon.yml validated (device=%s)", new_cfg.device)
        except Exception as exc:  # noqa: BLE001
            log.error("config_changed: daemon.yml re-validate failed: %s", exc)
            return

        # Step 3: restart the Windows service if any field changed
        if new_cfg != self._cfg:
            log.info("config_changed: config differs — requesting service restart")
            if sys.platform == "win32":
                try:
                    await asyncio.to_thread(subprocess.run, ["sc", "stop", "Hermes"],
                                            capture_output=True, timeout=30)
                    await asyncio.to_thread(subprocess.run, ["sc", "start", "Hermes"],
                                            capture_output=True, timeout=30)
                    log.info("config_changed: service restart requested")
                except Exception as exc:  # noqa: BLE001
                    log.error("config_changed: service restart failed: %s", exc)
            else:
                log.info("config_changed: non-Windows; manual restart required to "
                         "pick up config changes")
        else:
            log.info("config_changed: config unchanged after pull; no restart needed")


async def _publish(args: argparse.Namespace) -> int:
    nc = await nats.connect(args.nats)
    await nc.publish(args.subject, args.payload.encode())
    await nc.flush()
    await nc.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hermes.routing")
    sub = p.add_subparsers(dest="cmd", required=True)

    pub = sub.add_parser("publish")
    pub.add_argument("--nats", required=True)
    pub.add_argument("--subject", required=True)
    pub.add_argument("--payload", required=True)

    args = p.parse_args(argv)
    if args.cmd == "publish":
        return asyncio.run(_publish(args))
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
