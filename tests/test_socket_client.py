"""Integration tests for the async socket client.

All tests require a running container engine (Podman or Docker).
They skip gracefully when no socket is found.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

import pytest
from pocket_dock._socket_client import (
    create_container,
    detect_socket,
    exec_command,
    inspect_container,
    remove_container,
    start_container,
    stop_container,
)
from pocket_dock._socket_client import (
    ping as socket_ping,
)
from pocket_dock.errors import (
    ContainerNotFound,
    ContainerNotRunning,
    ImageNotFound,
    SocketConnectionError,
)

from .conftest import requires_engine

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

IMAGE = "pocket-dock/minimal"
LABEL_KEY = "pocket-dock.test"
LABEL_VALUE = "true"


# -- Helpers --


async def _create_and_start(socket_path: str) -> str:
    """Create and start a container, returning its ID."""
    cid = await create_container(
        socket_path,
        image=IMAGE,
        command=["sleep", "infinity"],
        labels={LABEL_KEY: LABEL_VALUE},
    )
    await start_container(socket_path, cid)
    return cid


async def _cleanup(socket_path: str, container_id: str) -> None:
    """Force-remove a container, ignoring errors."""
    with contextlib.suppress(ContainerNotFound, OSError):
        await remove_container(socket_path, container_id, force=True)


@pytest.fixture
async def running_container(socket_path: str) -> AsyncIterator[str]:
    """Create and start a container, yield its ID, then clean up."""
    cid = await _create_and_start(socket_path)
    try:
        yield cid
    finally:
        await _cleanup(socket_path, cid)


# -- Socket detection --


@requires_engine
def test_detect_socket_returns_path(socket_path: str) -> None:
    detected = detect_socket()
    assert detected is not None
    assert detected == socket_path


# -- Ping --


@requires_engine
async def test_ping_success(socket_path: str) -> None:
    result = await socket_ping(socket_path)
    assert result == "OK"


@requires_engine
async def test_ping_bad_socket() -> None:
    with pytest.raises(SocketConnectionError):
        await socket_ping("/tmp/nonexistent-pocket-dock-test.sock")


# -- Container lifecycle --


@requires_engine
async def test_create_container(socket_path: str) -> None:
    cid = await create_container(
        socket_path,
        image=IMAGE,
        command=["sleep", "infinity"],
        labels={LABEL_KEY: LABEL_VALUE},
    )
    try:
        assert isinstance(cid, str)
        assert len(cid) > 10
    finally:
        await _cleanup(socket_path, cid)


@requires_engine
async def test_start_container(socket_path: str) -> None:
    cid = await create_container(
        socket_path,
        image=IMAGE,
        command=["sleep", "infinity"],
        labels={LABEL_KEY: LABEL_VALUE},
    )
    try:
        await start_container(socket_path, cid)
        info = await inspect_container(socket_path, cid)
        assert info["State"]["Running"] is True
    finally:
        await _cleanup(socket_path, cid)


@requires_engine
async def test_stop_container(socket_path: str, running_container: str) -> None:
    await stop_container(socket_path, running_container, timeout=2)
    info = await inspect_container(socket_path, running_container)
    assert info["State"]["Running"] is False


@requires_engine
async def test_remove_container(socket_path: str) -> None:
    cid = await _create_and_start(socket_path)
    await stop_container(socket_path, cid, timeout=2)
    await remove_container(socket_path, cid)
    with pytest.raises(ContainerNotFound):
        await inspect_container(socket_path, cid)


@requires_engine
async def test_force_remove_running_container(socket_path: str) -> None:
    cid = await _create_and_start(socket_path)
    await remove_container(socket_path, cid, force=True)
    with pytest.raises(ContainerNotFound):
        await inspect_container(socket_path, cid)


@requires_engine
async def test_create_container_bad_image(socket_path: str) -> None:
    with pytest.raises(ImageNotFound):
        await create_container(
            socket_path,
            image="pocket-dock/nonexistent-image-xyz-12345",
            command=["sleep", "infinity"],
        )


# -- Exec --


@requires_engine
async def test_exec_simple_command(socket_path: str, running_container: str) -> None:
    result = await exec_command(socket_path, running_container, ["echo", "hello"])
    assert result.ok
    assert result.stdout.strip() == "hello"
    assert result.exit_code == 0


@requires_engine
async def test_exec_stderr(socket_path: str, running_container: str) -> None:
    result = await exec_command(socket_path, running_container, ["sh", "-c", "echo err >&2"])
    assert result.exit_code == 0
    assert "err" in result.stderr


@requires_engine
async def test_exec_nonzero_exit(socket_path: str, running_container: str) -> None:
    result = await exec_command(socket_path, running_container, ["sh", "-c", "exit 42"])
    assert result.exit_code == 42
    assert result.ok is False


@requires_engine
async def test_exec_on_stopped_container(socket_path: str) -> None:
    cid = await _create_and_start(socket_path)
    try:
        await stop_container(socket_path, cid, timeout=2)
        with pytest.raises(ContainerNotRunning):
            await exec_command(socket_path, cid, ["echo", "hello"])
    finally:
        await _cleanup(socket_path, cid)


@requires_engine
async def test_exec_on_removed_container(socket_path: str) -> None:
    cid = await _create_and_start(socket_path)
    await remove_container(socket_path, cid, force=True)
    with pytest.raises(ContainerNotFound):
        await exec_command(socket_path, cid, ["echo", "hello"])


# -- Stream demux --


@requires_engine
async def test_demux_stdout_only(socket_path: str, running_container: str) -> None:
    result = await exec_command(socket_path, running_container, ["echo", "just stdout"])
    assert "just stdout" in result.stdout
    assert result.stderr == ""


@requires_engine
async def test_demux_stderr_only(socket_path: str, running_container: str) -> None:
    result = await exec_command(socket_path, running_container, ["sh", "-c", "echo only-err >&2"])
    assert "only-err" in result.stderr


@requires_engine
async def test_demux_mixed_output(socket_path: str, running_container: str) -> None:
    result = await exec_command(
        socket_path,
        running_container,
        ["sh", "-c", "echo out && echo err >&2"],
    )
    assert "out" in result.stdout
    assert "err" in result.stderr


@requires_engine
async def test_demux_large_output(socket_path: str, running_container: str) -> None:
    result = await exec_command(
        socket_path,
        running_container,
        ["sh", "-c", "dd if=/dev/zero bs=1024 count=100 2>/dev/null | base64"],
    )
    assert result.ok
    assert len(result.stdout) > 10000


@requires_engine
async def test_demux_empty_output(socket_path: str, running_container: str) -> None:
    result = await exec_command(socket_path, running_container, ["true"])
    assert result.ok
    assert result.stdout == ""
    assert result.stderr == ""


# -- Inspect container --


@requires_engine
async def test_inspect_container(socket_path: str, running_container: str) -> None:
    info = await inspect_container(socket_path, running_container)
    assert info["State"]["Running"] is True
    assert LABEL_KEY in info["Config"]["Labels"]


@requires_engine
async def test_inspect_nonexistent_container(socket_path: str) -> None:
    with pytest.raises(ContainerNotFound):
        await inspect_container(socket_path, "nonexistent-container-id-xyz")


# -- Duration tracking --


@requires_engine
async def test_exec_duration_tracked(socket_path: str, running_container: str) -> None:
    result = await exec_command(socket_path, running_container, ["sleep", "0.1"])
    assert result.ok
    assert result.duration_ms >= 50  # at least some time passed


# -- Multiple execs on same container --


@requires_engine
async def test_multiple_sequential_execs(socket_path: str, running_container: str) -> None:
    r1 = await exec_command(socket_path, running_container, ["echo", "first"])
    r2 = await exec_command(socket_path, running_container, ["echo", "second"])
    assert r1.stdout.strip() == "first"
    assert r2.stdout.strip() == "second"


@requires_engine
async def test_concurrent_execs(socket_path: str, running_container: str) -> None:
    results = await asyncio.gather(
        exec_command(socket_path, running_container, ["echo", "a"]),
        exec_command(socket_path, running_container, ["echo", "b"]),
        exec_command(socket_path, running_container, ["echo", "c"]),
    )
    outputs = sorted(r.stdout.strip() for r in results)
    assert outputs == ["a", "b", "c"]
