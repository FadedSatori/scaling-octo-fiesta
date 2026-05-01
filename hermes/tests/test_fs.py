"""Tests for hermes.mcp_servers.fs."""
import pytest
from pathlib import Path
from fastapi import HTTPException
from hermes.mcp_servers.fs import FsServer


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def fs(tmp_root: Path) -> FsServer:
    return FsServer(roots=[tmp_root])


@pytest.mark.asyncio
class TestFsRead:
    async def test_read_existing_file(self, fs: FsServer, tmp_root: Path):
        f = tmp_root / "test.txt"
        f.write_text("hello world")
        result = await fs.call("read", {"path": str(f)})
        assert result == "hello world"

    async def test_read_respects_max_bytes(self, fs: FsServer, tmp_root: Path):
        f = tmp_root / "big.txt"
        f.write_bytes(b"x" * 1000)
        result = await fs.call("read", {"path": str(f), "max_bytes": 10})
        assert result == "x" * 10

    async def test_read_outside_root_rejected(self, fs: FsServer):
        with pytest.raises(HTTPException) as exc:
            await fs.call("read", {"path": "/etc/passwd"})
        assert exc.value.status_code == 403

    async def test_read_symlink_escape_rejected(self, fs: FsServer, tmp_root: Path):
        link = tmp_root / "escape"
        link.symlink_to("/etc")
        with pytest.raises(HTTPException) as exc:
            await fs.call("read", {"path": str(link / "passwd")})
        assert exc.value.status_code == 403

    async def test_read_nonexistent_file_raises_404(self, fs: FsServer, tmp_root: Path):
        with pytest.raises(HTTPException) as exc:
            await fs.call("read", {"path": str(tmp_root / "nope.txt")})
        assert exc.value.status_code == 404

    async def test_read_no_roots_configured(self, tmp_root: Path):
        empty_fs = FsServer(roots=[])
        with pytest.raises(HTTPException) as exc:
            await empty_fs.call("read", {"path": str(tmp_root / "x.txt")})
        assert exc.value.status_code == 403


@pytest.mark.asyncio
class TestFsWrite:
    async def test_write_creates_file(self, fs: FsServer, tmp_root: Path):
        p = tmp_root / "out.txt"
        result = await fs.call("write", {"path": str(p), "content": "data"})
        assert p.read_text() == "data"
        assert "4" in result  # "wrote 4 chars"

    async def test_write_creates_parents(self, fs: FsServer, tmp_root: Path):
        p = tmp_root / "a" / "b" / "c.txt"
        await fs.call("write", {"path": str(p), "content": "x"})
        assert p.exists()

    async def test_write_outside_root_rejected(self, fs: FsServer):
        with pytest.raises(HTTPException) as exc:
            await fs.call("write", {"path": "/tmp/evil.txt", "content": "x"})
        assert exc.value.status_code == 403

    async def test_write_overwrites_existing(self, fs: FsServer, tmp_root: Path):
        p = tmp_root / "over.txt"
        p.write_text("old")
        await fs.call("write", {"path": str(p), "content": "new"})
        assert p.read_text() == "new"


@pytest.mark.asyncio
class TestFsList:
    async def test_list_directory(self, fs: FsServer, tmp_root: Path):
        (tmp_root / "file.txt").write_text("x")
        (tmp_root / "subdir").mkdir()
        result = await fs.call("list", {"path": str(tmp_root)})
        lines = result.splitlines()
        assert any(l.startswith("f ") and "file.txt" in l for l in lines)
        assert any(l.startswith("d ") and "subdir" in l for l in lines)

    async def test_list_sorted_alphabetically(self, fs: FsServer, tmp_root: Path):
        (tmp_root / "zzz.txt").write_text("x")
        (tmp_root / "aaa.txt").write_text("x")
        result = await fs.call("list", {"path": str(tmp_root)})
        lines = result.splitlines()
        names = [l.split(" ", 1)[1] for l in lines]
        assert names == sorted(names)

    async def test_list_outside_root_rejected(self, fs: FsServer):
        with pytest.raises(HTTPException):
            await fs.call("list", {"path": "/etc"})

    async def test_list_nonexistent_raises_404(self, fs: FsServer, tmp_root: Path):
        with pytest.raises(HTTPException) as exc:
            await fs.call("list", {"path": str(tmp_root / "ghost_dir")})
        assert exc.value.status_code == 404


@pytest.mark.asyncio
class TestFsUnknownOp:
    async def test_unknown_op_raises(self, fs: FsServer, tmp_root: Path):
        with pytest.raises(HTTPException) as exc:
            await fs.call("delete", {"path": str(tmp_root)})
        assert exc.value.status_code == 400
