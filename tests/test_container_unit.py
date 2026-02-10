"""Unit tests for AsyncContainer, Container, and factory functions.

These tests do NOT require a running container engine.
"""

from __future__ import annotations

import io
import tarfile
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pocket_dock._async_container import (
    AsyncContainer,
    _build_command,
    _build_host_config,
    _generate_name,
)
from pocket_dock._async_container import (
    create_new_container as async_factory,
)
from pocket_dock._process import AsyncExecStream, AsyncProcess
from pocket_dock._stream import STREAM_STDOUT
from pocket_dock._sync_container import Container, SyncExecStream, SyncProcess, _LoopThread
from pocket_dock.errors import ContainerNotFound, ContainerNotRunning, PodmanNotRunning
from pocket_dock.types import ExecResult

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

# --- Name generation ---


def test_generate_name_format() -> None:
    name = _generate_name()
    assert name.startswith("pd-")
    assert len(name) == 11  # "pd-" + 8 hex chars


def test_generate_name_unique() -> None:
    names = {_generate_name() for _ in range(50)}
    assert len(names) == 50


# --- Command building ---


def test_build_command_shell() -> None:
    assert _build_command("echo hello", None) == ["sh", "-c", "echo hello"]


def test_build_command_python() -> None:
    assert _build_command("print(1)", "python") == ["python3", "-c", "print(1)"]


def test_build_command_unknown_lang_uses_shell() -> None:
    assert _build_command("foo", "ruby") == ["sh", "-c", "foo"]


# --- AsyncContainer properties ---


def test_async_container_properties() -> None:
    ac = AsyncContainer(
        "abc123",
        "/tmp/test.sock",
        name="pd-test1234",
        timeout=60,
    )
    assert ac.container_id == "abc123"
    assert ac.socket_path == "/tmp/test.sock"
    assert ac.name == "pd-test1234"


# --- AsyncContainer run delegates to exec_command ---


async def test_async_container_run_delegates() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-xx")
    expected = ExecResult(exit_code=0, stdout="hi\n")

    with patch(
        "pocket_dock._async_container.sc.exec_command",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = expected
        result = await ac.run("echo hi")

    assert result is expected
    mock.assert_called_once_with(
        "/tmp/s.sock",
        "cid",
        ["sh", "-c", "echo hi"],
        max_output=10 * 1024 * 1024,
        timeout=30,
    )


async def test_async_container_run_custom_timeout() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-xx")
    expected = ExecResult(exit_code=0)

    with patch(
        "pocket_dock._async_container.sc.exec_command",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = expected
        await ac.run("sleep 1", timeout=5)

    _, kwargs = mock.call_args
    assert kwargs["timeout"] == 5


async def test_async_container_run_python_lang() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-xx")
    expected = ExecResult(exit_code=0, stdout="3\n")

    with patch(
        "pocket_dock._async_container.sc.exec_command",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = expected
        await ac.run("print(1+2)", lang="python")

    args = mock.call_args[0]
    assert args[2] == ["python3", "-c", "print(1+2)"]


# --- AsyncContainer shutdown ---


async def test_async_shutdown_calls_stop_then_remove() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-xx")

    with (
        patch("pocket_dock._async_container.sc.stop_container", new_callable=AsyncMock) as stop,
        patch(
            "pocket_dock._async_container.sc.remove_container",
            new_callable=AsyncMock,
        ) as remove,
    ):
        await ac.shutdown()

    stop.assert_called_once_with("/tmp/s.sock", "cid")
    remove.assert_called_once_with("/tmp/s.sock", "cid", force=True)


async def test_async_shutdown_force_skips_stop() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-xx")

    with (
        patch("pocket_dock._async_container.sc.stop_container", new_callable=AsyncMock) as stop,
        patch(
            "pocket_dock._async_container.sc.remove_container",
            new_callable=AsyncMock,
        ) as remove,
    ):
        await ac.shutdown(force=True)

    stop.assert_not_called()
    remove.assert_called_once_with("/tmp/s.sock", "cid", force=True)


async def test_async_shutdown_idempotent() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-xx")

    with (
        patch("pocket_dock._async_container.sc.stop_container", new_callable=AsyncMock) as stop,
        patch(
            "pocket_dock._async_container.sc.remove_container",
            new_callable=AsyncMock,
        ),
    ):
        await ac.shutdown()
        await ac.shutdown()  # second call is no-op

    stop.assert_called_once()


# --- AsyncContainer context manager ---


async def test_async_context_manager_calls_shutdown() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-xx")

    with (
        patch("pocket_dock._async_container.sc.stop_container", new_callable=AsyncMock),
        patch("pocket_dock._async_container.sc.remove_container", new_callable=AsyncMock),
    ):
        async with ac as entered:
            assert entered is ac


# --- create_new_container (async) error paths ---


async def test_async_create_no_socket_raises() -> None:
    with (
        patch("pocket_dock._async_container.sc.detect_socket", return_value=None),
        pytest.raises(PodmanNotRunning),
    ):
        await async_factory()


async def test_async_create_sets_labels() -> None:
    with (
        patch(
            "pocket_dock._async_container.sc.detect_socket",
            return_value="/tmp/s.sock",
        ),
        patch(
            "pocket_dock._async_container.sc.create_container",
            new_callable=AsyncMock,
            return_value="deadbeef",
        ) as create,
        patch(
            "pocket_dock._async_container.sc.start_container",
            new_callable=AsyncMock,
        ),
    ):
        c = await async_factory(name="pd-lab")

    assert c.container_id == "deadbeef"
    assert c.name == "pd-lab"
    labels = create.call_args[1]["labels"]
    assert labels["pocket-dock.managed"] == "true"
    assert labels["pocket-dock.instance"] == "pd-lab"


# --- Container (sync) properties ---


def test_sync_container_properties() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-sync")
    lt = _LoopThread.get()
    c = Container(ac, lt)
    assert c.container_id == "cid"
    assert c.socket_path == "/tmp/s.sock"
    assert c.name == "pd-sync"


# --- Imports from top-level ---


def test_import_container_from_pocket_dock() -> None:
    from pocket_dock import Container, create_new_container

    assert Container is not None
    assert create_new_container is not None


def test_import_async_from_async_module() -> None:
    from pocket_dock.async_ import AsyncContainer, create_new_container

    assert AsyncContainer is not None
    assert create_new_container is not None


# --- AsyncContainer.read_file branch coverage ---


def _make_container() -> AsyncContainer:
    return AsyncContainer("cid", "/tmp/s.sock", name="pd-test")


async def test_read_file_skips_non_file_members() -> None:
    c = _make_container()

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        # Add a directory entry (non-file, will be skipped)
        dir_info = tarfile.TarInfo(name="somedir")
        dir_info.type = tarfile.DIRTYPE
        tar.addfile(dir_info)
        # Add the actual file
        info = tarfile.TarInfo(name="data.txt")
        content = b"hello"
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))

    with patch(
        "pocket_dock._async_container.sc.pull_archive",
        new_callable=AsyncMock,
        return_value=buf.getvalue(),
    ):
        result = await c.read_file("/tmp/data.txt")

    assert result == b"hello"


async def test_read_file_extractfile_returns_none() -> None:
    c = _make_container()

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(name="data.txt")
        content = b"hello"
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))

    with (
        patch(
            "pocket_dock._async_container.sc.pull_archive",
            new_callable=AsyncMock,
            return_value=buf.getvalue(),
        ),
        patch("tarfile.TarFile.extractfile", return_value=None),
        pytest.raises(FileNotFoundError, match="no file found"),
    ):
        await c.read_file("/tmp/data.txt")


# --- AsyncContainer.pull branch: single file with extractfile returning None ---


async def test_pull_single_file_extractfile_none() -> None:
    c = _make_container()

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(name="file.txt")
        content = b"data"
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))

    import tempfile

    with (
        patch(
            "pocket_dock._async_container.sc.pull_archive",
            new_callable=AsyncMock,
            return_value=buf.getvalue(),
        ),
        patch("tarfile.TarFile.extractfile", return_value=None),
        tempfile.TemporaryDirectory() as tmpdir,
    ):
        import pathlib

        dest = str(pathlib.Path(tmpdir) / "file.txt")
        await c.pull("/container/file.txt", dest)
        # Falls through to extractall since extractfile returned None
        assert pathlib.Path(dest).is_dir()  # noqa: ASYNC240


# --- _LoopThread coverage ---


def test_loopthread_loop_property() -> None:
    lt = _LoopThread.get()
    assert lt.loop is not None
    assert lt.loop.is_running()


def test_loopthread_shutdown() -> None:
    # Create a fresh instance (not the singleton) to test shutdown
    fresh = _LoopThread()
    assert fresh._thread.is_alive()
    fresh._shutdown()
    assert not fresh._thread.is_alive()


def test_loopthread_double_check_locking_race() -> None:
    original_instance = _LoopThread._instance
    original_lock = _LoopThread._lock

    class _SimulateRace:
        """A mock lock that simulates another thread winning the race."""

        def __enter__(self) -> _SimulateRace:  # noqa: PYI034
            # Simulate: between the outer check and lock acquisition,
            # another thread already created the singleton.
            _LoopThread._instance = original_instance
            return self

        def __exit__(self, *args: object) -> None:
            pass

    try:
        _LoopThread._instance = None
        _LoopThread._lock = _SimulateRace()  # type: ignore[assignment]
        result = _LoopThread.get()
        assert result is original_instance
    finally:
        _LoopThread._instance = original_instance
        _LoopThread._lock = original_lock


# --- _build_host_config ---


def test_build_host_config_no_limits() -> None:
    assert _build_host_config(0, 0) is None


def test_build_host_config_mem_only() -> None:
    hc = _build_host_config(256 * 1024 * 1024, 0)
    assert hc is not None
    assert hc["Memory"] == 256 * 1024 * 1024
    assert "NanoCpus" not in hc


def test_build_host_config_cpu_only() -> None:
    hc = _build_host_config(0, 500_000_000)
    assert hc is not None
    assert hc["NanoCpus"] == 500_000_000
    assert "Memory" not in hc


def test_build_host_config_both() -> None:
    hc = _build_host_config(128 * 1024**2, 250_000_000)
    assert hc is not None
    assert "Memory" in hc
    assert "NanoCpus" in hc


# --- AsyncContainer.info ---


async def test_async_info_running() -> None:
    ac = _make_container()
    inspect_data = {
        "Id": "cid",
        "Created": "2026-01-01T00:00:00Z",
        "State": {"Status": "running", "Running": True, "StartedAt": "2026-01-01T00:01:00Z"},
        "Config": {"Image": "test-image"},
        "NetworkSettings": {"IPAddress": "172.17.0.2"},
    }
    stats_data = {
        "memory_stats": {"usage": 1024, "limit": 4096},
        "pids_stats": {"current": 1},
    }
    top_data = {"Titles": ["PID"], "Processes": [["1"]]}

    with (
        patch(
            "pocket_dock._async_container.sc.inspect_container",
            new_callable=AsyncMock,
            return_value=inspect_data,
        ),
        patch(
            "pocket_dock._async_container.sc.get_container_stats",
            new_callable=AsyncMock,
            return_value=stats_data,
        ),
        patch(
            "pocket_dock._async_container.sc.get_container_top",
            new_callable=AsyncMock,
            return_value=top_data,
        ),
    ):
        info = await ac.info()

    assert info.status == "running"
    assert info.pids == 1
    assert info.network is True


async def test_async_info_stopped() -> None:
    ac = _make_container()
    inspect_data = {
        "Id": "cid",
        "Created": "2026-01-01T00:00:00Z",
        "State": {"Status": "exited", "Running": False},
        "Config": {"Image": "test-image"},
        "NetworkSettings": {"IPAddress": ""},
    }

    with patch(
        "pocket_dock._async_container.sc.inspect_container",
        new_callable=AsyncMock,
        return_value=inspect_data,
    ):
        info = await ac.info()

    assert info.status == "exited"
    assert info.memory_usage == ""
    assert info.pids == 0


async def test_async_info_race_container_stops_during_stats() -> None:
    ac = _make_container()
    inspect_data = {
        "Id": "cid",
        "Created": "2026-01-01T00:00:00Z",
        "State": {"Status": "running", "Running": True},
        "Config": {"Image": "test-image"},
        "NetworkSettings": {},
    }

    with (
        patch(
            "pocket_dock._async_container.sc.inspect_container",
            new_callable=AsyncMock,
            return_value=inspect_data,
        ),
        patch(
            "pocket_dock._async_container.sc.get_container_stats",
            new_callable=AsyncMock,
            side_effect=ContainerNotRunning("cid"),
        ),
        patch(
            "pocket_dock._async_container.sc.get_container_top",
            new_callable=AsyncMock,
        ),
    ):
        info = await ac.info()

    # Stats failed, but info should still return successfully
    assert info.memory_usage == ""


async def test_async_info_race_container_removed_during_stats() -> None:
    ac = _make_container()
    inspect_data = {
        "Id": "cid",
        "Created": "2026-01-01T00:00:00Z",
        "State": {"Status": "running", "Running": True},
        "Config": {"Image": "test-image"},
        "NetworkSettings": {},
    }

    with (
        patch(
            "pocket_dock._async_container.sc.inspect_container",
            new_callable=AsyncMock,
            return_value=inspect_data,
        ),
        patch(
            "pocket_dock._async_container.sc.get_container_stats",
            new_callable=AsyncMock,
            side_effect=ContainerNotFound("cid"),
        ),
        patch(
            "pocket_dock._async_container.sc.get_container_top",
            new_callable=AsyncMock,
        ),
    ):
        info = await ac.info()

    assert info.memory_usage == ""


# --- AsyncContainer.reboot ---


async def test_async_reboot_simple() -> None:
    ac = _make_container()

    with patch(
        "pocket_dock._async_container.sc.restart_container",
        new_callable=AsyncMock,
    ) as mock_restart:
        await ac.reboot()

    mock_restart.assert_called_once_with("/tmp/s.sock", "cid")


async def test_async_reboot_fresh() -> None:
    ac = AsyncContainer(
        "old_cid",
        "/tmp/s.sock",
        name="pd-test",
        image="test-image",
        mem_limit_bytes=256 * 1024**2,
        nano_cpus=500_000_000,
    )

    with (
        patch("pocket_dock._async_container.sc.stop_container", new_callable=AsyncMock),
        patch("pocket_dock._async_container.sc.remove_container", new_callable=AsyncMock),
        patch(
            "pocket_dock._async_container.sc.create_container",
            new_callable=AsyncMock,
            return_value="new_cid",
        ) as mock_create,
        patch("pocket_dock._async_container.sc.start_container", new_callable=AsyncMock),
    ):
        await ac.reboot(fresh=True)

    assert ac.container_id == "new_cid"
    # Verify resource limits are passed through
    call_kwargs = mock_create.call_args[1]
    assert call_kwargs["host_config"]["Memory"] == 256 * 1024**2
    assert call_kwargs["host_config"]["NanoCpus"] == 500_000_000


async def test_async_reboot_fresh_stop_already_stopped() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-test", image="img")

    with (
        patch(
            "pocket_dock._async_container.sc.stop_container",
            new_callable=AsyncMock,
            side_effect=ContainerNotRunning("cid"),
        ),
        patch("pocket_dock._async_container.sc.remove_container", new_callable=AsyncMock),
        patch(
            "pocket_dock._async_container.sc.create_container",
            new_callable=AsyncMock,
            return_value="new_cid",
        ),
        patch("pocket_dock._async_container.sc.start_container", new_callable=AsyncMock),
    ):
        await ac.reboot(fresh=True)

    assert ac.container_id == "new_cid"


async def test_async_reboot_fresh_remove_already_gone() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-test", image="img")

    with (
        patch("pocket_dock._async_container.sc.stop_container", new_callable=AsyncMock),
        patch(
            "pocket_dock._async_container.sc.remove_container",
            new_callable=AsyncMock,
            side_effect=ContainerNotFound("cid"),
        ),
        patch(
            "pocket_dock._async_container.sc.create_container",
            new_callable=AsyncMock,
            return_value="new_cid",
        ),
        patch("pocket_dock._async_container.sc.start_container", new_callable=AsyncMock),
    ):
        await ac.reboot(fresh=True)

    assert ac.container_id == "new_cid"


# --- create_new_container with resource limits ---


async def test_async_create_with_mem_limit() -> None:
    with (
        patch(
            "pocket_dock._async_container.sc.detect_socket",
            return_value="/tmp/s.sock",
        ),
        patch(
            "pocket_dock._async_container.sc.create_container",
            new_callable=AsyncMock,
            return_value="deadbeef",
        ) as mock_create,
        patch("pocket_dock._async_container.sc.start_container", new_callable=AsyncMock),
    ):
        c = await async_factory(name="pd-mem", mem_limit="256m")

    assert c.container_id == "deadbeef"
    call_kwargs = mock_create.call_args[1]
    assert call_kwargs["host_config"]["Memory"] == 256 * 1024**2


async def test_async_create_with_cpu_percent() -> None:
    with (
        patch(
            "pocket_dock._async_container.sc.detect_socket",
            return_value="/tmp/s.sock",
        ),
        patch(
            "pocket_dock._async_container.sc.create_container",
            new_callable=AsyncMock,
            return_value="deadbeef",
        ) as mock_create,
        patch("pocket_dock._async_container.sc.start_container", new_callable=AsyncMock),
    ):
        c = await async_factory(name="pd-cpu", cpu_percent=50)

    assert c.container_id == "deadbeef"
    call_kwargs = mock_create.call_args[1]
    assert call_kwargs["host_config"]["NanoCpus"] == 500_000_000


async def test_async_create_no_limits_no_host_config() -> None:
    with (
        patch(
            "pocket_dock._async_container.sc.detect_socket",
            return_value="/tmp/s.sock",
        ),
        patch(
            "pocket_dock._async_container.sc.create_container",
            new_callable=AsyncMock,
            return_value="deadbeef",
        ) as mock_create,
        patch("pocket_dock._async_container.sc.start_container", new_callable=AsyncMock),
    ):
        await async_factory(name="pd-nolimits")

    call_kwargs = mock_create.call_args[1]
    assert call_kwargs["host_config"] is None


# --- AsyncContainer new properties ---


def test_async_container_new_properties() -> None:
    ac = AsyncContainer(
        "cid",
        "/tmp/s.sock",
        name="pd-test",
        image="my-image",
        mem_limit_bytes=100,
        nano_cpus=200,
    )
    assert ac._image == "my-image"
    assert ac._mem_limit_bytes == 100
    assert ac._nano_cpus == 200


# --- Sync Container.info and reboot ---


def test_sync_info_delegates() -> None:
    ac = _make_container()
    lt = _LoopThread.get()
    c = Container(ac, lt)

    inspect_data = {
        "Id": "cid",
        "Created": "2026-01-01T00:00:00Z",
        "State": {"Status": "exited", "Running": False},
        "Config": {"Image": "test-image"},
        "NetworkSettings": {"IPAddress": ""},
    }

    with patch(
        "pocket_dock._async_container.sc.inspect_container",
        new_callable=AsyncMock,
        return_value=inspect_data,
    ):
        info = c.info()

    assert info.status == "exited"


def test_sync_reboot_delegates() -> None:
    ac = _make_container()
    lt = _LoopThread.get()
    c = Container(ac, lt)

    with patch(
        "pocket_dock._async_container.sc.restart_container",
        new_callable=AsyncMock,
    ) as mock_restart:
        c.reboot()

    mock_restart.assert_called_once()


# --- Helpers for stream/detach tests ---


async def _gen_from_list(
    items: list[tuple[int, bytes]],
) -> AsyncGenerator[tuple[int, bytes], None]:
    for item in items:
        yield item


def _mock_writer() -> MagicMock:
    writer = MagicMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    return writer


# --- run(stream=True) ---


async def test_async_run_stream_returns_exec_stream() -> None:
    ac = _make_container()
    writer = _mock_writer()
    frames = [(STREAM_STDOUT, b"hello")]

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list(frames), writer),
        ),
        patch(
            "pocket_dock._socket_client._exec_inspect_exit_code",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        stream = await ac.run("echo hello", stream=True)
        assert isinstance(stream, AsyncExecStream)
        chunks = [chunk async for chunk in stream]

    assert len(chunks) == 1
    assert chunks[0].data == "hello"
    assert stream in ac._active_streams


# --- run(detach=True) ---


async def test_async_run_detach_returns_process() -> None:
    ac = _make_container()
    writer = _mock_writer()
    frames = [(STREAM_STDOUT, b"out")]

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list(frames), writer),
        ),
        patch(
            "pocket_dock._socket_client._exec_inspect_exit_code",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        proc = await ac.run("echo out", detach=True)
        assert isinstance(proc, AsyncProcess)
        result = await proc.wait()

    assert result.stdout == "out"
    assert proc in ac._active_processes


# --- stream + detach raises ValueError ---


async def test_async_run_stream_and_detach_raises() -> None:
    ac = _make_container()
    with pytest.raises(ValueError, match="mutually exclusive"):
        await ac.run("echo x", stream=True, detach=True)


# --- Callback registration ---


async def test_async_on_stdout_callback() -> None:
    ac = _make_container()
    captured: list[str] = []
    ac.on_stdout(lambda _c, data: captured.append(data))

    writer = _mock_writer()
    frames = [(STREAM_STDOUT, b"hello")]

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list(frames), writer),
        ),
        patch(
            "pocket_dock._socket_client._exec_inspect_exit_code",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        proc = await ac.run("echo hello", detach=True)
        await proc.wait()

    assert "hello" in captured


async def test_async_on_stderr_callback() -> None:
    ac = _make_container()
    captured: list[str] = []
    ac.on_stderr(lambda _c, data: captured.append(data))

    from pocket_dock._stream import STREAM_STDERR

    writer = _mock_writer()
    frames = [(STREAM_STDERR, b"err")]

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list(frames), writer),
        ),
        patch(
            "pocket_dock._socket_client._exec_inspect_exit_code",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        proc = await ac.run("echo err >&2", detach=True)
        await proc.wait()

    assert "err" in captured


async def test_async_on_exit_callback() -> None:
    ac = _make_container()
    exit_codes: list[int] = []
    ac.on_exit(lambda _c, code: exit_codes.append(code))

    writer = _mock_writer()

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list([]), writer),
        ),
        patch(
            "pocket_dock._socket_client._exec_inspect_exit_code",
            new_callable=AsyncMock,
            return_value=42,
        ),
    ):
        proc = await ac.run("exit 42", detach=True)
        await proc.wait()

    assert exit_codes == [42]


# --- shutdown cleans up streams and processes ---


async def test_async_shutdown_cleans_up_streams() -> None:
    ac = _make_container()
    writer = _mock_writer()

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list([]), writer),
        ),
    ):
        await ac.run("echo x", stream=True)

    with (
        patch("pocket_dock._async_container.sc.stop_container", new_callable=AsyncMock),
        patch("pocket_dock._async_container.sc.remove_container", new_callable=AsyncMock),
    ):
        await ac.shutdown()

    assert len(ac._active_streams) == 0
    writer.close.assert_called_once()


async def test_async_shutdown_cleans_up_processes() -> None:
    ac = _make_container()
    writer = _mock_writer()
    frames = [(STREAM_STDOUT, b"x")]

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list(frames), writer),
        ),
        patch(
            "pocket_dock._socket_client._exec_inspect_exit_code",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        proc = await ac.run("echo x", detach=True)
        await proc.wait()

    with (
        patch("pocket_dock._async_container.sc.stop_container", new_callable=AsyncMock),
        patch("pocket_dock._async_container.sc.remove_container", new_callable=AsyncMock),
    ):
        await ac.shutdown()

    assert len(ac._active_processes) == 0


# --- Sync SyncExecStream ---


async def test_sync_exec_stream_iteration() -> None:
    writer = _mock_writer()
    frames = [(STREAM_STDOUT, b"hi")]

    with patch(
        "pocket_dock._socket_client._exec_inspect_exit_code",
        new_callable=AsyncMock,
        return_value=0,
    ):
        async_stream = AsyncExecStream("eid", _gen_from_list(frames), writer, "/tmp/s.sock", 0.0)
        lt = _LoopThread.get()
        sync_stream = SyncExecStream(async_stream, lt)
        chunks = list(sync_stream)

    assert len(chunks) == 1
    assert chunks[0].data == "hi"
    assert sync_stream.result.exit_code == 0


# --- Sync SyncProcess (tested via Container.run(detach=True)) ---


def test_sync_process_basic() -> None:
    ac = _make_container()
    lt = _LoopThread.get()
    c = Container(ac, lt)
    writer = _mock_writer()
    frames = [(STREAM_STDOUT, b"hello")]

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list(frames), writer),
        ),
        patch(
            "pocket_dock._socket_client._exec_inspect_exit_code",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        proc = c.run("echo hello", detach=True)
        assert proc.id == "eid"
        result = proc.wait()

    assert result.exit_code == 0
    assert result.stdout == "hello"
    snap = proc.peek()
    assert snap.stdout == "hello"


def test_sync_process_read_drains() -> None:
    ac = _make_container()
    lt = _LoopThread.get()
    c = Container(ac, lt)
    writer = _mock_writer()
    frames = [(STREAM_STDOUT, b"data")]

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list(frames), writer),
        ),
        patch(
            "pocket_dock._socket_client._exec_inspect_exit_code",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        proc = c.run("echo data", detach=True)
        proc.wait()

    snap = proc.read()
    assert snap.stdout == "data"
    snap2 = proc.read()
    assert snap2.stdout == ""


def test_sync_process_buffer_props() -> None:
    ac = _make_container()
    lt = _LoopThread.get()
    c = Container(ac, lt)
    writer = _mock_writer()
    frames = [(STREAM_STDOUT, b"x" * 100)]

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list(frames), writer),
        ),
        patch(
            "pocket_dock._socket_client._exec_inspect_exit_code",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        proc = c.run("echo x", detach=True)
        proc.wait()

    assert proc.buffer_overflow is False
    assert proc.buffer_size > 0


def test_sync_process_is_running() -> None:
    ac = _make_container()
    lt = _LoopThread.get()
    c = Container(ac, lt)
    writer = _mock_writer()

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list([]), writer),
        ),
        patch(
            "pocket_dock._socket_client._exec_inspect_exit_code",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        proc = c.run("true", detach=True)
        proc.wait()

    assert proc.is_running() is False


def test_sync_process_kill() -> None:
    ac = _make_container()
    lt = _LoopThread.get()
    c = Container(ac, lt)
    writer = _mock_writer()

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list([]), writer),
        ),
        patch(
            "pocket_dock._socket_client._exec_inspect_exit_code",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        proc = c.run("true", detach=True)
        proc.wait()
        # Kill on already-finished process is no-op
        proc.kill()


# --- Sync Container.run(stream=True) and Container.run(detach=True) ---


def test_sync_container_run_stream() -> None:
    ac = _make_container()
    lt = _LoopThread.get()
    c = Container(ac, lt)
    writer = _mock_writer()
    frames = [(STREAM_STDOUT, b"hi")]

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list(frames), writer),
        ),
        patch(
            "pocket_dock._socket_client._exec_inspect_exit_code",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        stream = c.run("echo hi", stream=True)
        assert isinstance(stream, SyncExecStream)
        chunks = list(stream)

    assert len(chunks) == 1
    assert chunks[0].data == "hi"


def test_sync_container_run_detach() -> None:
    ac = _make_container()
    lt = _LoopThread.get()
    c = Container(ac, lt)
    writer = _mock_writer()
    frames = [(STREAM_STDOUT, b"out")]

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list(frames), writer),
        ),
        patch(
            "pocket_dock._socket_client._exec_inspect_exit_code",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        proc = c.run("echo out", detach=True)
        assert isinstance(proc, SyncProcess)
        result = proc.wait()

    assert result.stdout == "out"


# --- Sync Container callback delegation ---


def test_sync_container_on_stdout() -> None:
    ac = _make_container()
    lt = _LoopThread.get()
    c = Container(ac, lt)
    captured: list[str] = []
    c.on_stdout(lambda _c, data: captured.append(data))

    writer = _mock_writer()
    frames = [(STREAM_STDOUT, b"hello")]

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list(frames), writer),
        ),
        patch(
            "pocket_dock._socket_client._exec_inspect_exit_code",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        proc = c.run("echo hello", detach=True)
        proc.wait()

    assert "hello" in captured


def test_sync_container_on_stderr() -> None:
    from pocket_dock._stream import STREAM_STDERR

    ac = _make_container()
    lt = _LoopThread.get()
    c = Container(ac, lt)
    captured: list[str] = []
    c.on_stderr(lambda _c, data: captured.append(data))

    writer = _mock_writer()
    frames = [(STREAM_STDERR, b"err")]

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list(frames), writer),
        ),
        patch(
            "pocket_dock._socket_client._exec_inspect_exit_code",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        proc = c.run("echo err >&2", detach=True)
        proc.wait()

    assert "err" in captured


def test_sync_container_on_exit() -> None:
    ac = _make_container()
    lt = _LoopThread.get()
    c = Container(ac, lt)
    exit_codes: list[int] = []
    c.on_exit(lambda _c, code: exit_codes.append(code))

    writer = _mock_writer()

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list([]), writer),
        ),
        patch(
            "pocket_dock._socket_client._exec_inspect_exit_code",
            new_callable=AsyncMock,
            return_value=7,
        ),
    ):
        proc = c.run("exit 7", detach=True)
        proc.wait()

    assert exit_codes == [7]


# --- Exports ---


def test_exports_exec_stream_alias() -> None:
    from pocket_dock import ExecStream

    assert ExecStream is SyncExecStream


def test_exports_process_alias() -> None:
    from pocket_dock import Process

    assert Process is SyncProcess


def test_exports_async_exec_stream() -> None:
    from pocket_dock.async_ import AsyncExecStream as ExportedStream

    assert ExportedStream is AsyncExecStream


def test_exports_async_process() -> None:
    from pocket_dock.async_ import AsyncProcess as ExportedProc

    assert ExportedProc is AsyncProcess


# --- Persist property ---


def test_async_container_persist_default() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-test")
    assert ac.persist is False


def test_async_container_persist_true() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-test", persist=True)
    assert ac.persist is True


def test_sync_container_persist_delegates() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-test", persist=True)
    lt = _LoopThread.get()
    c = Container(ac, lt)
    assert c.persist is True


# --- Shutdown with persist ---


async def test_async_shutdown_persist_stops_but_does_not_remove() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-xx", persist=True)

    with (
        patch("pocket_dock._async_container.sc.stop_container", new_callable=AsyncMock) as stop,
        patch(
            "pocket_dock._async_container.sc.remove_container",
            new_callable=AsyncMock,
        ) as remove,
    ):
        await ac.shutdown()

    stop.assert_called_once_with("/tmp/s.sock", "cid")
    remove.assert_not_called()


async def test_async_shutdown_persist_force_still_stops_only() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-xx", persist=True)

    with (
        patch("pocket_dock._async_container.sc.stop_container", new_callable=AsyncMock) as stop,
        patch(
            "pocket_dock._async_container.sc.remove_container",
            new_callable=AsyncMock,
        ) as remove,
    ):
        await ac.shutdown(force=True)

    stop.assert_called_once_with("/tmp/s.sock", "cid")
    remove.assert_not_called()


async def test_async_shutdown_persist_idempotent() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-xx", persist=True)

    with (
        patch("pocket_dock._async_container.sc.stop_container", new_callable=AsyncMock) as stop,
        patch(
            "pocket_dock._async_container.sc.remove_container",
            new_callable=AsyncMock,
        ),
    ):
        await ac.shutdown()
        await ac.shutdown()

    stop.assert_called_once()


# --- Snapshot ---


async def test_async_snapshot_with_tag() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-xx")

    with patch(
        "pocket_dock._async_container.sc.commit_container",
        new_callable=AsyncMock,
        return_value="sha256:img",
    ) as mock:
        result = await ac.snapshot("myrepo:v1")

    assert result == "sha256:img"
    mock.assert_called_once_with("/tmp/s.sock", "cid", "myrepo", "v1")


async def test_async_snapshot_no_tag_defaults_latest() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-xx")

    with patch(
        "pocket_dock._async_container.sc.commit_container",
        new_callable=AsyncMock,
        return_value="sha256:img",
    ) as mock:
        await ac.snapshot("myrepo")

    mock.assert_called_once_with("/tmp/s.sock", "cid", "myrepo", "latest")


async def test_async_snapshot_image_with_registry() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-xx")

    with patch(
        "pocket_dock._async_container.sc.commit_container",
        new_callable=AsyncMock,
        return_value="sha256:img",
    ) as mock:
        await ac.snapshot("registry.io/repo:v2")

    mock.assert_called_once_with("/tmp/s.sock", "cid", "registry.io/repo", "v2")


def test_sync_snapshot_delegates() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-xx")
    lt = _LoopThread.get()
    c = Container(ac, lt)

    with patch(
        "pocket_dock._async_container.sc.commit_container",
        new_callable=AsyncMock,
        return_value="sha256:img",
    ):
        result = c.snapshot("myrepo:v1")

    assert result == "sha256:img"


# --- Create with persist and volumes ---


async def test_async_create_with_persist() -> None:
    with (
        patch(
            "pocket_dock._async_container.sc.detect_socket",
            return_value="/tmp/s.sock",
        ),
        patch(
            "pocket_dock._async_container.sc.create_container",
            new_callable=AsyncMock,
            return_value="deadbeef",
        ) as create,
        patch("pocket_dock._async_container.sc.start_container", new_callable=AsyncMock),
    ):
        c = await async_factory(name="pd-persist", persist=True)

    assert c.persist is True
    labels = create.call_args[1]["labels"]
    assert labels["pocket-dock.persist"] == "true"
    assert "pocket-dock.created-at" in labels


async def test_async_create_without_persist_label() -> None:
    with (
        patch(
            "pocket_dock._async_container.sc.detect_socket",
            return_value="/tmp/s.sock",
        ),
        patch(
            "pocket_dock._async_container.sc.create_container",
            new_callable=AsyncMock,
            return_value="deadbeef",
        ) as create,
        patch("pocket_dock._async_container.sc.start_container", new_callable=AsyncMock),
    ):
        c = await async_factory(name="pd-eph")

    assert c.persist is False
    labels = create.call_args[1]["labels"]
    assert labels["pocket-dock.persist"] == "false"


async def test_async_create_with_volumes() -> None:
    with (
        patch(
            "pocket_dock._async_container.sc.detect_socket",
            return_value="/tmp/s.sock",
        ),
        patch(
            "pocket_dock._async_container.sc.create_container",
            new_callable=AsyncMock,
            return_value="deadbeef",
        ) as create,
        patch("pocket_dock._async_container.sc.start_container", new_callable=AsyncMock),
    ):
        await async_factory(name="pd-vol", volumes={"/host/path": "/container/path"})

    hc = create.call_args[1]["host_config"]
    assert "/host/path:/container/path" in hc["Binds"]


async def test_async_create_volumes_without_resource_limits() -> None:
    with (
        patch(
            "pocket_dock._async_container.sc.detect_socket",
            return_value="/tmp/s.sock",
        ),
        patch(
            "pocket_dock._async_container.sc.create_container",
            new_callable=AsyncMock,
            return_value="deadbeef",
        ) as create,
        patch("pocket_dock._async_container.sc.start_container", new_callable=AsyncMock),
    ):
        await async_factory(name="pd-vol2", volumes={"/a": "/b"})

    hc = create.call_args[1]["host_config"]
    assert hc is not None
    assert "/a:/b" in hc["Binds"]


async def test_async_create_volumes_with_resource_limits() -> None:
    with (
        patch(
            "pocket_dock._async_container.sc.detect_socket",
            return_value="/tmp/s.sock",
        ),
        patch(
            "pocket_dock._async_container.sc.create_container",
            new_callable=AsyncMock,
            return_value="deadbeef",
        ) as create,
        patch("pocket_dock._async_container.sc.start_container", new_callable=AsyncMock),
    ):
        await async_factory(
            name="pd-vol3",
            mem_limit="256m",
            volumes={"/a": "/b"},
        )

    hc = create.call_args[1]["host_config"]
    assert hc["Memory"] == 256 * 1024**2
    assert "/a:/b" in hc["Binds"]


# --- Reboot with persist labels ---


async def test_reboot_fresh_includes_persist_labels() -> None:
    ac = AsyncContainer(
        "cid", "/tmp/s.sock", name="pd-xx", image="pocket-dock/minimal", persist=True
    )

    with (
        patch("pocket_dock._async_container.sc.stop_container", new_callable=AsyncMock),
        patch("pocket_dock._async_container.sc.remove_container", new_callable=AsyncMock),
        patch(
            "pocket_dock._async_container.sc.create_container",
            new_callable=AsyncMock,
            return_value="newcid",
        ) as create,
        patch("pocket_dock._async_container.sc.start_container", new_callable=AsyncMock),
    ):
        await ac.reboot(fresh=True)

    assert ac.container_id == "newcid"
    labels = create.call_args[1]["labels"]
    assert labels["pocket-dock.persist"] == "true"
    assert "pocket-dock.created-at" in labels


# --- Project properties ---


def test_async_container_project_default() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-test")
    assert ac.project == ""
    assert ac.data_path == ""


def test_async_container_project_set() -> None:
    ac = AsyncContainer(
        "cid", "/tmp/s.sock", name="pd-test", project="my-proj", data_path="/some/path"
    )
    assert ac.project == "my-proj"
    assert ac.data_path == "/some/path"


def test_sync_container_project_delegates() -> None:
    ac = AsyncContainer(
        "cid", "/tmp/s.sock", name="pd-test", project="proj", data_path="/dp"
    )
    lt = _LoopThread.get()
    c = Container(ac, lt)
    assert c.project == "proj"
    assert c.data_path == "/dp"


async def test_async_create_with_project_label() -> None:
    with (
        patch(
            "pocket_dock._async_container.sc.detect_socket",
            return_value="/tmp/s.sock",
        ),
        patch(
            "pocket_dock._async_container.sc.create_container",
            new_callable=AsyncMock,
            return_value="deadbeef",
        ) as create,
        patch("pocket_dock._async_container.sc.start_container", new_callable=AsyncMock),
        patch("pocket_dock.projects.find_project_root", return_value=None),
    ):
        c = await async_factory(name="pd-proj", persist=True, project="my-project")

    labels = create.call_args[1]["labels"]
    assert labels["pocket-dock.project"] == "my-project"
    assert c._project == "my-project"


async def test_async_reboot_fresh_preserves_project_labels() -> None:
    ac = AsyncContainer(
        "cid",
        "/tmp/s.sock",
        name="pd-xx",
        image="pocket-dock/minimal",
        persist=True,
        project="my-proj",
        data_path="/data/path",
    )

    with (
        patch("pocket_dock._async_container.sc.stop_container", new_callable=AsyncMock),
        patch("pocket_dock._async_container.sc.remove_container", new_callable=AsyncMock),
        patch(
            "pocket_dock._async_container.sc.create_container",
            new_callable=AsyncMock,
            return_value="newcid",
        ) as create,
        patch("pocket_dock._async_container.sc.start_container", new_callable=AsyncMock),
    ):
        await ac.reboot(fresh=True)

    labels = create.call_args[1]["labels"]
    assert labels["pocket-dock.project"] == "my-proj"
    assert labels["pocket-dock.data-path"] == "/data/path"
