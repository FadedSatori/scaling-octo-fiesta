"""Tests for hermes.routing — NatsRouter config_changed handler."""
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest

from hermes.daemon.__main__ import DaemonConfig
from hermes.routing import NatsRouter


def _make_router(cfg: DaemonConfig | None = None) -> NatsRouter:
    fake_agent = MagicMock()
    return NatsRouter(url="nats://127.0.0.1:4222", device="g14",
                      agent=fake_agent, cfg=cfg)


def _make_msg(data: dict) -> MagicMock:
    msg = MagicMock()
    msg.data = json.dumps(data).encode()
    return msg


@pytest.mark.asyncio
class TestOnConfigChanged:
    async def test_no_cfg_logs_warning_and_returns(self, caplog):
        router = _make_router(cfg=None)
        with pytest.raises(Exception) if False else patch("hermes.routing.log") as log:
            await router._on_config_changed(_make_msg({"by": "test"}))
            log.warning.assert_called_once()
            assert "no cfg" in log.warning.call_args[0][0]

    async def test_missing_repo_root_logs_warning(self, tmp_path: Path):
        cfg = DaemonConfig(device="g14", repo_root="/nonexistent/path/xyz")
        router = _make_router(cfg=cfg)
        with patch("hermes.routing.log") as log:
            await router._on_config_changed(_make_msg({}))
            log.warning.assert_called()
            assert any("not found" in str(c) for c in log.warning.call_args_list)

    async def test_git_pull_called_with_correct_args(self, tmp_path: Path):
        # Create a fake git repo root
        repo = tmp_path / "repo"
        repo.mkdir()
        cfg = DaemonConfig(device="g14", repo_root=str(repo))
        router = _make_router(cfg=cfg)

        fake_result = MagicMock()
        fake_result.returncode = 0
        fake_result.stdout = "Already up to date."
        fake_result.stderr = ""

        # Also need a daemon.yml next to repo/
        daemon_yml = tmp_path / "daemon.yml"
        daemon_yml.write_text(f'device: "g14"\nrepo_root: "{repo}"\n')

        with patch("hermes.routing.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = fake_result
            with patch("hermes.routing.log"):
                await router._on_config_changed(_make_msg({"by": "ci", "msg": "test"}))

        # First call should be git pull
        first_call_args = mock_thread.call_args_list[0][0]
        assert first_call_args[0] == subprocess.run
        assert first_call_args[1] == ["git", "-C", str(repo), "pull", "--ff-only"]

    async def test_git_pull_failure_stops_processing(self, tmp_path: Path):
        repo = tmp_path / "repo"
        repo.mkdir()
        cfg = DaemonConfig(device="g14", repo_root=str(repo))
        router = _make_router(cfg=cfg)

        fail_result = MagicMock()
        fail_result.returncode = 1
        fail_result.stderr = "merge conflict"

        with patch("hermes.routing.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = fail_result
            with patch("hermes.routing.log") as log:
                await router._on_config_changed(_make_msg({}))
                log.error.assert_called()
        # Only one to_thread call (the git pull) — no sc stop/start
        assert mock_thread.call_count == 1

    async def test_no_restart_when_config_unchanged(self, tmp_path: Path):
        repo = tmp_path / "repo"
        repo.mkdir()
        cfg = DaemonConfig(device="g14", repo_root=str(repo))
        router = _make_router(cfg=cfg)

        ok_result = MagicMock()
        ok_result.returncode = 0
        ok_result.stdout = "Already up to date."

        daemon_yml = tmp_path / "daemon.yml"
        daemon_yml.write_text(f'device: "g14"\nrepo_root: "{repo}"\n')

        with patch("hermes.routing.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = ok_result
            with patch("hermes.routing.log") as log:
                await router._on_config_changed(_make_msg({}))
            # Should log "config unchanged"
            assert any("unchanged" in str(c) for c in log.info.call_args_list)
        # No sc stop/start calls (only git pull)
        assert mock_thread.call_count == 1

    async def test_invalid_json_payload_handled_gracefully(self, tmp_path: Path):
        cfg = DaemonConfig(device="g14", repo_root="/nonexistent/path")
        router = _make_router(cfg=cfg)
        msg = MagicMock()
        msg.data = b"{invalid json"
        with patch("hermes.routing.log"):
            # Should not raise
            await router._on_config_changed(msg)

    async def test_empty_payload_handled_gracefully(self, tmp_path: Path):
        cfg = DaemonConfig(device="g14", repo_root="/nonexistent/path")
        router = _make_router(cfg=cfg)
        msg = MagicMock()
        msg.data = b""
        with patch("hermes.routing.log"):
            await router._on_config_changed(msg)


class TestNatsRouterInit:
    def test_cfg_stored(self):
        cfg = DaemonConfig(device="g14")
        router = _make_router(cfg=cfg)
        assert router._cfg is cfg

    def test_no_cfg_default(self):
        router = _make_router()
        assert router._cfg is None
