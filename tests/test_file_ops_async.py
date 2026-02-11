"""Integration tests for async file operations (write_file, read_file, list_files, push, pull)."""

from __future__ import annotations

import pathlib
import tempfile

import pytest
from pocketdock._async_container import create_new_container

from .conftest import requires_engine

# --- write_file + read_file ---


@requires_engine
async def test_write_and_read_text() -> None:
    async with await create_new_container() as c:
        await c.write_file("/tmp/hello.txt", "hello world")
        data = await c.read_file("/tmp/hello.txt")
        assert data == b"hello world"


@requires_engine
async def test_write_and_read_binary() -> None:
    async with await create_new_container() as c:
        payload = bytes(range(256))
        await c.write_file("/tmp/binary.bin", payload)
        data = await c.read_file("/tmp/binary.bin")
        assert data == payload


@requires_engine
async def test_write_creates_parent_dirs() -> None:
    async with await create_new_container() as c:
        await c.write_file("/tmp/a/b/c/deep.txt", "nested")
        data = await c.read_file("/tmp/a/b/c/deep.txt")
        assert data == b"nested"


@requires_engine
async def test_write_overwrites_existing() -> None:
    async with await create_new_container() as c:
        await c.write_file("/tmp/over.txt", "first")
        await c.write_file("/tmp/over.txt", "second")
        data = await c.read_file("/tmp/over.txt")
        assert data == b"second"


@requires_engine
async def test_read_nonexistent_file() -> None:
    async with await create_new_container() as c:
        with pytest.raises(FileNotFoundError):
            await c.read_file("/tmp/no-such-file.txt")


# --- list_files ---


@requires_engine
async def test_list_files_default_home() -> None:
    async with await create_new_container() as c:
        files = await c.list_files()
        assert isinstance(files, list)


@requires_engine
async def test_list_files_shows_written_file() -> None:
    async with await create_new_container() as c:
        await c.write_file("/tmp/listed.txt", "content")
        files = await c.list_files("/tmp")
        assert "listed.txt" in files


@requires_engine
async def test_list_files_excludes_dot_entries() -> None:
    async with await create_new_container() as c:
        files = await c.list_files("/tmp")
        assert "." not in files
        assert ".." not in files


@requires_engine
async def test_list_files_nonexistent_dir() -> None:
    async with await create_new_container() as c:
        try:
            await c.list_files("/no/such/dir")
        except FileNotFoundError:
            pass
        else:
            pytest.fail("Expected FileNotFoundError for nonexistent directory")


# --- push (host → container) ---


@requires_engine
async def test_push_file() -> None:
    async with await create_new_container() as c:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"from host")
            f.flush()
            host_path = f.name

        await c.push(host_path, f"/tmp/{pathlib.Path(host_path).name}")
        data = await c.read_file(f"/tmp/{pathlib.Path(host_path).name}")
        assert data == b"from host"
        pathlib.Path(host_path).unlink()  # noqa: ASYNC240


@requires_engine
async def test_push_directory() -> None:
    async with await create_new_container() as c:
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.txt").write_text("aaa")
            (pathlib.Path(tmpdir) / "b.txt").write_text("bbb")
            dir_name = pathlib.Path(tmpdir).name
            await c.push(tmpdir, f"/tmp/{dir_name}")

        files = await c.list_files(f"/tmp/{dir_name}")
        assert "a.txt" in files
        assert "b.txt" in files


@requires_engine
async def test_push_nonexistent_source() -> None:
    async with await create_new_container() as c:
        try:
            await c.push("/no/such/path", "/tmp/dest")
        except FileNotFoundError:
            pass
        else:
            pytest.fail("Expected FileNotFoundError for nonexistent source")


# --- pull (container → host) ---


@requires_engine
async def test_pull_file() -> None:
    async with await create_new_container() as c:
        await c.write_file("/tmp/pullme.txt", "pulled content")
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = str(pathlib.Path(tmpdir) / "pullme.txt")
            await c.pull("/tmp/pullme.txt", dest)
            assert pathlib.Path(dest).read_bytes() == b"pulled content"  # noqa: ASYNC240


@requires_engine
async def test_pull_directory() -> None:
    async with await create_new_container() as c:
        await c.run("mkdir -p /tmp/pulldir && echo x > /tmp/pulldir/x.txt")
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = str(pathlib.Path(tmpdir) / "pulldir")
            await c.pull("/tmp/pulldir", dest)
            assert pathlib.Path(dest).is_dir()  # noqa: ASYNC240


# --- Round trip ---


@requires_engine
async def test_write_read_roundtrip_utf8() -> None:
    async with await create_new_container() as c:
        text = "Unicode: \u00e9\u00e0\u00fc \u4f60\u597d \U0001f680"
        await c.write_file("/tmp/utf8.txt", text)
        data = await c.read_file("/tmp/utf8.txt")
        assert data.decode("utf-8") == text
