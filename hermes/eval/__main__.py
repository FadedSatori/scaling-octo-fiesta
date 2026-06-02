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
import json
import logging
import sys
from pathlib import Path
from typing import TypedDict

import httpx
import nats

from hermes.daemon.__main__ import load_config
from hermes.daemon.installer import wait_for_daemon

log = logging.getLogger("hermes.eval")

EVAL_PROMPTS: list[tuple[str, str]] = [
    # (prompt, expected_substring_in_final — empty string means any non-empty answer passes)
    ("list the files in the current working directory", ""),
    ("echo 'hermes eval ok' to stdout via the shell tool", "hermes eval ok"),
]

INCUMBENT_FILE = "eval_incumbent.json"
PROMOTION_THRESHOLD = 2.0  # percentage points


class Incumbent(TypedDict):
    model: str
    score: float


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


def _load_incumbent(repo_root: Path) -> Incumbent:
    """Load incumbent model score. Returns defaults if missing."""
    incumbent_file = repo_root / INCUMBENT_FILE
    if incumbent_file.exists():
        try:
            with incumbent_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("failed to load incumbent: %s", exc)
    return {"model": "none", "score": 0.0}


def _save_incumbent(repo_root: Path, incumbent: Incumbent) -> None:
    """Persist model and score as the new incumbent."""
    incumbent_file = repo_root / INCUMBENT_FILE
    try:
        with incumbent_file.open("w", encoding="utf-8") as f:
            json.dump(incumbent, f)
        log.info("saved incumbent: model=%s score=%.1f%%", incumbent["model"], incumbent["score"] * 100)
    except OSError as exc:
        log.error("failed to save incumbent: %s", exc)


async def _maybe_promote_model(
    repo_root: Path,
    nats_url: str,
    new_model: str,
    new_score: float,
    incumbent: Incumbent,
    skip: bool,
) -> None:
    """Compare new score vs incumbent and promote if threshold exceeded."""
    incumbent_score = incumbent["score"]
    if incumbent_score == 0:
        log.info("no incumbent found; initializing baseline")
        _save_incumbent(repo_root, {"model": new_model, "score": new_score})
        return

    improvement_pct = (new_score - incumbent_score) / incumbent_score * 100
    log.info("score vs incumbent (model=%s score=%.1f%%): improvement=%.1f%%",
             incumbent["model"], incumbent_score * 100, improvement_pct)

    if improvement_pct < PROMOTION_THRESHOLD:
        return

    if skip:
        log.info("threshold met (%.1f%%) but --skip-promotion set", improvement_pct)
        return

    log.info("threshold met (%.1f%%) — promoting model", improvement_pct)
    try:
        nc = await nats.connect(nats_url)
        payload = json.dumps({
            "model": new_model,
            "score": new_score,
            "improvement_pct": improvement_pct,
        })
        await nc.publish("hermes.events.model_promoted", payload.encode())
        await nc.flush()
        await nc.close()
        log.info("published model_promoted: model=%s improvement=%.1f%%", new_model, improvement_pct)
    except OSError as exc:
        log.error("failed to publish model_promoted: %s", exc)

    _save_incumbent(repo_root, {"model": new_model, "score": new_score})


async def main_async(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    base = f"http://127.0.0.1:{cfg.bind_port}"
    log.info("waiting for daemon at %s", base)
    await wait_for_daemon(base)

    model_name = args.model or cfg.agent_model
    log.info("running eval (model=%s)", model_name)
    results = await run_eval(base, args.model)
    new_score = float(results["score"])
    log.info(
        "eval: %d/%d passed  score=%.1f%%",
        results["passed"], results["total"], new_score * 100,
    )

    repo_root = Path(cfg.repo_root)
    incumbent = _load_incumbent(repo_root)
    await _maybe_promote_model(
        repo_root=repo_root,
        nats_url=cfg.nats_url,
        new_model=model_name,
        new_score=new_score,
        incumbent=incumbent,
        skip=args.skip_promotion,
    )

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
    p.add_argument("--skip-promotion", action="store_true",
        help="Skip model promotion logic even if threshold is met")
    args = p.parse_args()
    logging.basicConfig(
        level=args.log_level,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
