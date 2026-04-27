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
import sys
from typing import TYPE_CHECKING, Any

import nats

if TYPE_CHECKING:
    from hermes.agent.loop import AgentLoop

log = logging.getLogger("hermes.routing")


class NatsRouter:
    def __init__(self, *, url: str, device: str, agent: "AgentLoop") -> None:
        self.url = url
        self.device = device
        self.agent = agent
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
