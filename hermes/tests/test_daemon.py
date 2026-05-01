"""Tests for hermes.daemon.__main__ (DaemonConfig, load_config)."""
import pytest
from pathlib import Path
from hermes.daemon.__main__ import DaemonConfig, load_config


class TestDaemonConfig:
    def test_defaults(self):
        cfg = DaemonConfig(device="g14")
        assert cfg.bind_host == "0.0.0.0"
        assert cfg.bind_port == 8765
        assert cfg.nats_url == "nats://127.0.0.1:4222"
        assert cfg.ollama_url == "http://127.0.0.1:11434"
        assert cfg.agent_model == "hermes3:8b"
        assert cfg.fs_roots == []

    def test_repo_root_is_string(self):
        cfg = DaemonConfig(device="g14")
        assert isinstance(cfg.repo_root, str)
        assert len(cfg.repo_root) > 0

    def test_repo_root_default_points_to_repo(self):
        cfg = DaemonConfig(device="g14")
        # The default resolves 3 levels above __main__.py:
        # hermes/daemon/__main__.py -> hermes/daemon/ -> hermes/ -> repo/
        repo = Path(cfg.repo_root)
        assert (repo / "hermes").is_dir()

    def test_equality_for_config_changed_detection(self):
        a = DaemonConfig(device="g14", bind_port=8765)
        b = DaemonConfig(device="g14", bind_port=8765)
        assert a == b

    def test_inequality_detected(self):
        a = DaemonConfig(device="g14", bind_port=8765)
        b = DaemonConfig(device="g14", bind_port=9999)
        assert a != b

    def test_custom_repo_root(self):
        cfg = DaemonConfig(device="g14", repo_root="/tmp/myrepo")
        assert cfg.repo_root == "/tmp/myrepo"


class TestLoadConfig:
    def test_load_minimal_yaml(self, tmp_path: Path):
        yaml_content = 'device: "g14"\n'
        f = tmp_path / "daemon.yml"
        f.write_text(yaml_content)
        cfg = load_config(f)
        assert cfg.device == "g14"
        assert cfg.bind_port == 8765  # default

    def test_load_full_yaml(self, tmp_path: Path):
        yaml_content = """
device: "lenovo"
bind_port: 9000
nats_url: "nats://g14.hermes-net:4222"
ollama_url: "http://127.0.0.1:11434"
agent_model: "hermes3:8b"
coder_model: "qwen2.5-coder:14b"
fs_roots:
  - "C:/Users/user/Documents/hermes"
repo_root: "C:/Users/user/AppData/Local/Hermes/repo"
"""
        f = tmp_path / "daemon.yml"
        f.write_text(yaml_content)
        cfg = load_config(f)
        assert cfg.device == "lenovo"
        assert cfg.bind_port == 9000
        assert cfg.nats_url == "nats://g14.hermes-net:4222"
        assert cfg.fs_roots == ["C:/Users/user/Documents/hermes"]
        assert cfg.repo_root == "C:/Users/user/AppData/Local/Hermes/repo"

    def test_load_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(Exception):
            load_config(tmp_path / "nonexistent.yml")

    def test_load_invalid_yaml_raises(self, tmp_path: Path):
        f = tmp_path / "bad.yml"
        f.write_text(": : :")
        with pytest.raises(Exception):
            load_config(f)
