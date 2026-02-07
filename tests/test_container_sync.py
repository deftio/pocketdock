"""Integration tests for Container (sync facade)."""

from __future__ import annotations

from pocket_dock import Container, create_new_container
from pocket_dock.types import ExecResult

from .conftest import requires_engine

# --- Factory & lifecycle ---


@requires_engine
def test_create_and_shutdown() -> None:
    c = create_new_container()
    assert isinstance(c, Container)
    assert c.container_id
    assert c.name.startswith("pd-")
    c.shutdown()


@requires_engine
def test_create_custom_name() -> None:
    c = create_new_container(name="pd-sync-custom")
    assert c.name == "pd-sync-custom"
    c.shutdown()


@requires_engine
def test_context_manager() -> None:
    with create_new_container() as c:
        result = c.run("echo hello")
        assert result.ok


# --- run() basics ---


@requires_engine
def test_run_echo() -> None:
    with create_new_container() as c:
        result = c.run("echo hello")
        assert isinstance(result, ExecResult)
        assert result.ok
        assert result.exit_code == 0
        assert result.stdout.strip() == "hello"
        assert result.stderr == ""
        assert result.duration_ms > 0


@requires_engine
def test_run_stderr() -> None:
    with create_new_container() as c:
        result = c.run("echo err >&2")
        assert result.ok
        assert result.stderr.strip() == "err"


@requires_engine
def test_run_nonzero_exit() -> None:
    with create_new_container() as c:
        result = c.run("exit 42")
        assert not result.ok
        assert result.exit_code == 42


@requires_engine
def test_run_python() -> None:
    with create_new_container() as c:
        result = c.run("print(1 + 2)", lang="python")
        assert result.ok
        assert result.stdout.strip() == "3"


# --- Timeout ---


@requires_engine
def test_run_timeout() -> None:
    with create_new_container() as c:
        result = c.run("sleep 60", timeout=1)
        assert not result.ok
        assert result.timed_out
        assert result.exit_code == -1


# --- Shutdown ---


@requires_engine
def test_shutdown_idempotent() -> None:
    c = create_new_container()
    c.shutdown()
    c.shutdown()  # no-op


@requires_engine
def test_shutdown_force() -> None:
    c = create_new_container()
    c.shutdown(force=True)
