"""Integration tests for sync file operations (write_file, read_file, list_files, push, pull)."""

from __future__ import annotations

import pathlib
import tempfile

import pytest
from pocketdock import Container, create_new_container

from .conftest import requires_engine

# --- write_file + read_file ---


@requires_engine
def test_sync_write_and_read_text() -> None:
    with create_new_container() as c:
        assert isinstance(c, Container)
        c.write_file("/tmp/hello.txt", "hello sync")
        data = c.read_file("/tmp/hello.txt")
        assert data == b"hello sync"


@requires_engine
def test_sync_write_and_read_binary() -> None:
    with create_new_container() as c:
        payload = bytes(range(256))
        c.write_file("/tmp/binary.bin", payload)
        data = c.read_file("/tmp/binary.bin")
        assert data == payload


# --- list_files ---


@requires_engine
def test_sync_list_files() -> None:
    with create_new_container() as c:
        c.write_file("/tmp/syncfile.txt", "content")
        files = c.list_files("/tmp")
        assert "syncfile.txt" in files


# --- push + pull ---


@requires_engine
def test_sync_push_and_pull() -> None:
    with create_new_container() as c:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"sync host data")
            f.flush()
            host_path = f.name
            fname = pathlib.Path(host_path).name

        c.push(host_path, f"/tmp/{fname}")
        data = c.read_file(f"/tmp/{fname}")
        assert data == b"sync host data"

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = str(pathlib.Path(tmpdir) / fname)
            c.pull(f"/tmp/{fname}", dest)
            assert pathlib.Path(dest).read_bytes() == b"sync host data"

        pathlib.Path(host_path).unlink()


@requires_engine
def test_sync_push_nonexistent_raises() -> None:
    with create_new_container() as c, pytest.raises(FileNotFoundError):
        c.push("/no/such/file", "/tmp/dest")
