"""hermes.eval — offline model evaluation harness (v0.1 stub).

Runs smoke prompts against the local daemon and reports a pass/fail score.
Full benchmark suite (task set, regression detection, auto-promotion) is
planned for v0.2.

Usage:
    python -m hermes.eval --config /path/to/daemon.yml [--model hermes3:8b]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import httpx

from hermes.daemon.__main__ import load_config
from hermes.daemon.installer import wait_for_daemon

log = logging.getLogger("hermes.eval")

EVAL_PROMPTS: list[tuple[str, str]] = [
    # (prompt, expected_substring_in_final — empty string means any non-empty answer passes)
    ("list the files in the current working directory", ""),
    ("echo 'hermes eval ok' to stdout via the shell tool", "hermes eval ok"),
]


async def run_eval(daemon_url: str, model: str | None) -> dict[str, object]:
    passed = failed = 0
    async with httpx.AsyncClient(timeout=120.0) as client:
        for prompt, expected in EVAL_PROMPTS:
            payload: dict[str, object] = {"prompt": prompt, "max_steps": 4}
            if model:
                payload["model"] = model
            try:
                r = await client.post(f"{daemon_url}/agent/run", json=payload)
                r.raise_for_status()
                final: str = r.json().get("final") or ""
                if final and (not expected or expected in final):
                    log.info("PASS: %r", prompt)
                    passed += 1
                else:
                    log.warning("FAIL: %r -> final=%r", prompt, final)
                    failed += 1
            except Exception as exc:  # noqa: BLE001
                log.error("FAIL (exception): %r -> %s", prompt, exc)
                failed += 1
    total = passed + failed
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "score": passed / total if total else 0.0,
    }


async def main_async(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    base = f"http://127.0.0.1:{cfg.bind_port}"
    log.info("waiting for daemon at %s", base)
    await wait_for_daemon(base)
    log.info("running eval (model=%s)", args.model or "default")
    results = await run_eval(base, args.model)
    log.info(
        "eval: %d/%d passed  score=%.1f%%",
        results["passed"], results["total"], float(results["score"]) * 100,
    )
    # v0.2 TODO: compare score vs incumbent; publish hermes.events.model_promoted if +2%
    return 0 if results["failed"] == 0 else 1


def main() -> int:
    p = argparse.ArgumentParser(
        prog="hermes.eval",
        description="Offline model evaluation for the Hermes daemon.",
    )
    p.add_argument("--model", default=None,
        help="Ollama model tag to evaluate (default: agent_model from daemon config)")
    p.add_argument("--config", required=True, type=Path,
        help="Path to rendered daemon.yml")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(
        level=args.log_level,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
