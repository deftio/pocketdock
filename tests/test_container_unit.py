"""Unit tests for AsyncContainer, Container, and factory functions.

These tests do NOT require a running container engine.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pocket_dock._async_container import (
    AsyncContainer,
    _build_command,
    _generate_name,
)
from pocket_dock._async_container import (
    create_new_container as async_factory,
)
from pocket_dock._sync_container import Container, _LoopThread
from pocket_dock.errors import PodmanNotRunning
from pocket_dock.types import ExecResult

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
