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


def _load_incumbent(repo_root: Path) -> dict[str, object]:
    """Load incumbent model score from eval_incumbent.json. Returns defaults if missing."""
    incumbent_file = repo_root / "eval_incumbent.json"
    if incumbent_file.exists():
        try:
            with incumbent_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:  # noqa: BLE001
            log.warning("failed to load incumbent: %s", exc)
    return {"model": "none", "score": 0.0}


def _save_incumbent(repo_root: Path, model: str, score: float) -> None:
    """Save model and score as the new incumbent."""
    incumbent_file = repo_root / "eval_incumbent.json"
    try:
        with incumbent_file.open("w", encoding="utf-8") as f:
            json.dump({"model": model, "score": score}, f)
        log.info("saved incumbent: model=%s score=%.1f%%", model, score * 100)
    except Exception as exc:  # noqa: BLE001
        log.error("failed to save incumbent: %s", exc)


async def _publish_model_promoted(nats_url: str, model: str, score: float, improvement_pct: float) -> None:
    """Publish hermes.events.model_promoted to NATS."""
    try:
        nc = await nats.connect(nats_url)
        payload = json.dumps({
            "model": model,
            "score": score,
            "improvement_pct": improvement_pct,
        })
        await nc.publish("hermes.events.model_promoted", payload.encode())
        await nc.flush()
        await nc.close()
        log.info("published model_promoted: model=%s improvement=%.1f%%", model, improvement_pct)
    except Exception as exc:  # noqa: BLE001
        log.error("failed to publish model_promoted: %s", exc)


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
    incumbent_score = float(incumbent.get("score", 0.0))

    if incumbent_score > 0:
        improvement_pct = (new_score - incumbent_score) / incumbent_score * 100
        log.info("score vs incumbent (model=%s score=%.1f%%): improvement=%.1f%%",
                 incumbent.get("model"), incumbent_score * 100, improvement_pct)
        if improvement_pct >= 2.0 and not args.skip_promotion:
            log.info("threshold met (+2.0%%) — promoting model")
            await _publish_model_promoted(cfg.nats_url, model_name, new_score, improvement_pct)
            _save_incumbent(repo_root, model_name, new_score)
        elif improvement_pct >= 2.0 and args.skip_promotion:
            log.info("threshold met (+2.0%%) but --skip-promotion set; not promoting")
    else:
        log.info("no incumbent found; initializing with current model")
        _save_incumbent(repo_root, model_name, new_score)

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
