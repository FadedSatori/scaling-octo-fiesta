"""Hermes installer agent — runs once after bootstrap to verify install,
register with the mesh, and run smoke tests. The same agent is used for
later self-updates.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import httpx

from hermes.daemon.__main__ import load_config

log = logging.getLogger("hermes.installer")

SMOKE_PROMPTS = [
    "list the files in the current working directory",
    "echo 'hermes installer ok' to stdout via the shell tool",
]


async def wait_for_daemon(url: str, timeout: float = 60.0) -> None:
    start = asyncio.get_event_loop().time()
    async with httpx.AsyncClient(timeout=2.0) as client:
        while True:
            try:
                r = await client.get(f"{url}/healthz")
                if r.status_code == 200:
                    return
            except Exception:
                pass
            if asyncio.get_event_loop().time() - start > timeout:
                raise TimeoutError(f"daemon at {url} did not respond within {timeout}s")
            await asyncio.sleep(1.0)


async def smoke(url: str) -> int:
    fails = 0
    async with httpx.AsyncClient(timeout=120.0) as client:
        for prompt in SMOKE_PROMPTS:
            r = await client.post(f"{url}/agent/run", json={"prompt": prompt, "max_steps": 4})
            if r.status_code != 200:
                log.error("smoke: %r -> HTTP %d", prompt, r.status_code)
                fails += 1
                continue
            data = r.json()
            if not data.get("final"):
                log.error("smoke: %r -> no final answer", prompt)
                fails += 1
            else:
                log.info("smoke: %r -> ok", prompt)
    return fails


async def run(cfg_path: Path, device: str) -> int:
    cfg = load_config(cfg_path)
    base = f"http://127.0.0.1:{cfg.bind_port}"
    log.info("waiting for daemon at %s", base)
    await wait_for_daemon(base)
    log.info("daemon up; running smoke tests")
    fails = await smoke(base)
    if fails:
        log.error("installer: %d smoke test(s) failed", fails)
        return 1
    log.info("installer: all smoke tests passed; device=%s ready", device)
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True, type=Path)
    p.add_argument("--device", required=True)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    return asyncio.run(run(args.config, args.device))


if __name__ == "__main__":
    raise SystemExit(main())
