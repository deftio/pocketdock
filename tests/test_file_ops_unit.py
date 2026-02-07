"""Unit tests for file operation methods (no container engine required)."""

from __future__ import annotations

import io
import pathlib
import tarfile
import tempfile
from unittest.mock import AsyncMock, patch

import pytest
from pocket_dock._async_container import AsyncContainer
from pocket_dock.types import ExecResult


def _make_container() -> AsyncContainer:
    return AsyncContainer("cid", "/tmp/s.sock", name="pd-test")


# --- write_file ---


async def test_write_file_text_encodes_utf8() -> None:
    c = _make_container()

    with patch(
        "pocket_dock._async_container.sc.push_archive",
        new_callable=AsyncMock,
    ) as mock_push:
        await c.write_file("/tmp/hello.txt", "hello")

    mock_push.assert_called_once()
    _, _, dest_dir, tar_data = mock_push.call_args[0]
    assert dest_dir == "/tmp"

    buf = io.BytesIO(tar_data)
    with tarfile.open(fileobj=buf, mode="r") as tar:
        members = tar.getmembers()
        assert len(members) == 1
        assert members[0].name == "hello.txt"
        extracted = tar.extractfile(members[0])
        assert extracted is not None
        assert extracted.read() == b"hello"


async def test_write_file_binary_passthrough() -> None:
    c = _make_container()
    payload = bytes(range(256))

    with patch(
        "pocket_dock._async_container.sc.push_archive",
        new_callable=AsyncMock,
    ) as mock_push:
        await c.write_file("/data/out.bin", payload)

    _, _, dest_dir, tar_data = mock_push.call_args[0]
    assert dest_dir == "/data"

    buf = io.BytesIO(tar_data)
    with tarfile.open(fileobj=buf, mode="r") as tar:
        extracted = tar.extractfile(tar.getmembers()[0])
        assert extracted is not None
        assert extracted.read() == payload


async def test_write_file_nested_path() -> None:
    c = _make_container()

    with patch(
        "pocket_dock._async_container.sc.push_archive",
        new_callable=AsyncMock,
    ) as mock_push:
        await c.write_file("/a/b/c/file.txt", "nested")

    _, _, dest_dir, _ = mock_push.call_args[0]
    assert dest_dir == "/a/b/c"


# --- read_file ---


async def test_read_file_extracts_from_tar() -> None:
    c = _make_container()

    # Build a tar archive containing one file
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(name="data.txt")
        content = b"file contents"
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    tar_bytes = buf.getvalue()

    with patch(
        "pocket_dock._async_container.sc.pull_archive",
        new_callable=AsyncMock,
        return_value=tar_bytes,
    ):
        result = await c.read_file("/tmp/data.txt")

    assert result == b"file contents"


async def test_read_file_empty_tar_raises() -> None:
    c = _make_container()

    # Build an empty tar archive (no files)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w"):
        pass
    empty_tar = buf.getvalue()

    with (
        patch(
            "pocket_dock._async_container.sc.pull_archive",
            new_callable=AsyncMock,
            return_value=empty_tar,
        ),
        pytest.raises(FileNotFoundError, match="no file found"),
    ):
        await c.read_file("/tmp/missing.txt")


# --- list_files ---


async def test_list_files_parses_output() -> None:
    c = _make_container()
    mock_result = ExecResult(exit_code=0, stdout=".\n..\nfoo.txt\nbar.txt\n")

    with patch.object(c, "run", new_callable=AsyncMock, return_value=mock_result):
        files = await c.list_files("/tmp")

    assert files == ["foo.txt", "bar.txt"]


async def test_list_files_failure_raises() -> None:
    c = _make_container()
    mock_result = ExecResult(exit_code=2, stderr="ls: cannot access: No such file")

    with (
        patch.object(c, "run", new_callable=AsyncMock, return_value=mock_result),
        pytest.raises(FileNotFoundError, match="ls failed"),
    ):
        await c.list_files("/no/such/dir")


async def test_list_files_default_path() -> None:
    c = _make_container()
    mock_result = ExecResult(exit_code=0, stdout=".\n..\n")

    with patch.object(c, "run", new_callable=AsyncMock, return_value=mock_result) as mock_run:
        files = await c.list_files()

    mock_run.assert_called_once_with("ls -1a /home/sandbox")
    assert files == []


# --- push ---


async def test_push_file_creates_tar() -> None:
    c = _make_container()

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"host file")
        f.flush()
        host_path = f.name

    try:
        with patch(
            "pocket_dock._async_container.sc.push_archive",
            new_callable=AsyncMock,
        ) as mock_push:
            await c.push(host_path, f"/container/{pathlib.Path(host_path).name}")

        mock_push.assert_called_once()
        _, _, dest_dir, tar_data = mock_push.call_args[0]
        assert dest_dir == "/container"

        buf = io.BytesIO(tar_data)
        with tarfile.open(fileobj=buf, mode="r") as tar:
            members = tar.getmembers()
            assert len(members) == 1
            extracted = tar.extractfile(members[0])
            assert extracted is not None
            assert extracted.read() == b"host file"
    finally:
        pathlib.Path(host_path).unlink()  # noqa: ASYNC240


async def test_push_directory_creates_tar() -> None:
    c = _make_container()

    with tempfile.TemporaryDirectory() as tmpdir:
        (pathlib.Path(tmpdir) / "a.txt").write_text("aaa")
        dir_name = pathlib.Path(tmpdir).name

        with patch(
            "pocket_dock._async_container.sc.push_archive",
            new_callable=AsyncMock,
        ) as mock_push:
            await c.push(tmpdir, f"/dest/{dir_name}")

        mock_push.assert_called_once()
        _, _, dest_dir, tar_data = mock_push.call_args[0]
        assert dest_dir == "/dest"

        buf = io.BytesIO(tar_data)
        with tarfile.open(fileobj=buf, mode="r") as tar:
            names = tar.getnames()
            assert any("a.txt" in n for n in names)


async def test_push_nonexistent_raises() -> None:
    c = _make_container()

    with pytest.raises(FileNotFoundError, match="source path does not exist"):
        await c.push("/no/such/path", "/dest/file")


# --- pull ---


async def test_pull_single_file() -> None:
    c = _make_container()

    # Build tar with one file
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(name="pulled.txt")
        content = b"pulled data"
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    tar_bytes = buf.getvalue()

    with (
        patch(
            "pocket_dock._async_container.sc.pull_archive",
            new_callable=AsyncMock,
            return_value=tar_bytes,
        ),
        tempfile.TemporaryDirectory() as tmpdir,
    ):
        dest = str(pathlib.Path(tmpdir) / "pulled.txt")
        await c.pull("/container/pulled.txt", dest)
        assert pathlib.Path(dest).read_bytes() == b"pulled data"  # noqa: ASYNC240


async def test_pull_directory() -> None:
    c = _make_container()

    # Build tar with a directory entry and a file inside it
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        dir_info = tarfile.TarInfo(name="mydir")
        dir_info.type = tarfile.DIRTYPE
        tar.addfile(dir_info)

        file_info = tarfile.TarInfo(name="mydir/x.txt")
        content = b"xdata"
        file_info.size = len(content)
        tar.addfile(file_info, io.BytesIO(content))
    tar_bytes = buf.getvalue()

    with (
        patch(
            "pocket_dock._async_container.sc.pull_archive",
            new_callable=AsyncMock,
            return_value=tar_bytes,
        ),
        tempfile.TemporaryDirectory() as tmpdir,
    ):
        dest = str(pathlib.Path(tmpdir) / "mydir")
        await c.pull("/container/mydir", dest)
        assert pathlib.Path(dest).is_dir()  # noqa: ASYNC240
        assert (pathlib.Path(dest) / "mydir" / "x.txt").read_bytes() == b"xdata"
