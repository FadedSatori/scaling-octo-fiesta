"""Entry point: `python -m hermes.daemon --config <path>`."""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

import uvicorn
import yaml
from fastapi import FastAPI
from pydantic import BaseModel

from hermes.agent.loop import AgentLoop
from hermes.mcp_servers.fs import FsServer
from hermes.mcp_servers.shell import ShellServer
from hermes.mcp_servers.inference import InferenceServer
from hermes.routing import NatsRouter

log = logging.getLogger("hermes.daemon")


class DaemonConfig(BaseModel):
    device: str
    bind_host: str = "0.0.0.0"
    bind_port: int = 8765
    nats_url: str = "nats://127.0.0.1:4222"
    ollama_url: str = "http://127.0.0.1:11434"
    coder_model: str = "qwen2.5-coder:14b"
    agent_model: str = "hermes3:8b"
    fs_roots: list[str] = []


def load_config(path: Path) -> DaemonConfig:
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return DaemonConfig.model_validate(raw)


def build_app(cfg: DaemonConfig) -> FastAPI:
    app = FastAPI(title="Hermes", version="0.1.0")

    fs = FsServer(roots=[Path(p) for p in cfg.fs_roots])
    shell = ShellServer()
    inference = InferenceServer(
        ollama_url=cfg.ollama_url,
        coder_model=cfg.coder_model,
        agent_model=cfg.agent_model,
    )
    agent = AgentLoop(
        inference=inference,
        tools={"fs": fs, "shell": shell},
    )

    app.state.fs = fs
    app.state.shell = shell
    app.state.inference = inference
    app.state.agent = agent
    app.state.cfg = cfg

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True, "device": cfg.device, "version": "0.1.0"}

    fs.mount(app, prefix="/mcp/fs")
    shell.mount(app, prefix="/mcp/shell")
    inference.mount(app, prefix="/mcp/inference")
    agent.mount(app, prefix="/agent")

    return app


async def run_router(cfg: DaemonConfig, app: FastAPI) -> None:
    router = NatsRouter(url=cfg.nats_url, device=cfg.device, agent=app.state.agent)
    await router.connect()
    app.state.router = router
    await router.serve()


def main() -> int:
    parser = argparse.ArgumentParser(prog="hermes-daemon")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    cfg = load_config(args.config)
    log.info("Hermes daemon starting; device=%s port=%d", cfg.device, cfg.bind_port)

    app = build_app(cfg)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    router_task = loop.create_task(run_router(cfg, app))

    config = uvicorn.Config(
        app,
        host=cfg.bind_host,
        port=cfg.bind_port,
        log_level=args.log_level.lower(),
        loop="asyncio",
    )
    server = uvicorn.Server(config)

    def _shutdown(*_: object) -> None:
        log.info("Shutdown signal received")
        server.should_exit = True
        router_task.cancel()

    if sys.platform != "win32":
        loop.add_signal_handler(signal.SIGTERM, _shutdown)
        loop.add_signal_handler(signal.SIGINT, _shutdown)
    else:
        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGBREAK, _shutdown)  # type: ignore[attr-defined]

    try:
        loop.run_until_complete(server.serve())
    finally:
        router_task.cancel()
        loop.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
