"""Integration tests for session functionality.

Requires a running container engine (Podman or Docker).
"""

from __future__ import annotations

import pytest
from pocketdock.async_ import AsyncContainer, create_new_container

from .conftest import requires_engine


@pytest.fixture
async def container() -> AsyncContainer:
    c = await create_new_container()
    yield c  # type: ignore[misc]
    await c.shutdown()


# --- Basic session ---


@requires_engine
async def test_session_send_and_wait_echo(container: AsyncContainer) -> None:
    sess = await container.session()
    result = await sess.send_and_wait("echo hello")
    assert result.ok
    assert result.stdout.strip() == "hello"
    await sess.close()


# --- State persistence ---


@requires_engine
async def test_session_cwd_persists(container: AsyncContainer) -> None:
    sess = await container.session()
    await sess.send_and_wait("cd /tmp")
    result = await sess.send_and_wait("pwd")
    assert result.ok
    assert result.stdout.strip() == "/tmp"
    await sess.close()


@requires_engine
async def test_session_env_var_persists(container: AsyncContainer) -> None:
    sess = await container.session()
    await sess.send_and_wait("export MY_VAR=pocketdock_test")
    result = await sess.send_and_wait("echo $MY_VAR")
    assert result.ok
    assert result.stdout.strip() == "pocketdock_test"
    await sess.close()


# --- Multiple sequential commands ---


@requires_engine
async def test_session_multiple_commands(container: AsyncContainer) -> None:
    sess = await container.session()

    r1 = await sess.send_and_wait("echo first")
    assert r1.ok
    assert r1.stdout.strip() == "first"

    r2 = await sess.send_and_wait("echo second")
    assert r2.ok
    assert r2.stdout.strip() == "second"

    r3 = await sess.send_and_wait("echo third")
    assert r3.ok
    assert r3.stdout.strip() == "third"

    await sess.close()


# --- Nonzero exit code ---


@requires_engine
async def test_session_nonzero_exit(container: AsyncContainer) -> None:
    sess = await container.session()
    result = await sess.send_and_wait("exit_code_test_cmd_does_not_exist 2>/dev/null; true")
    # The `true` at the end makes exit code 0
    assert result.exit_code == 0

    # Now test actual failure
    result2 = await sess.send_and_wait("false")
    assert result2.exit_code == 1
    assert result2.ok is False
    await sess.close()


# --- Stderr ---


@requires_engine
async def test_session_stderr_capture(container: AsyncContainer) -> None:
    sess = await container.session()
    # Small sleep ensures stderr frame arrives before the sentinel on stdout.
    result = await sess.send_and_wait("echo err >&2; sleep 0.05")
    assert result.ok
    assert "err" in result.stderr
    await sess.close()


# --- Timeout ---


@requires_engine
async def test_session_send_and_wait_timeout(container: AsyncContainer) -> None:
    sess = await container.session()
    result = await sess.send_and_wait("sleep 30", timeout=0.5)
    assert result.timed_out is True
    assert result.exit_code == -1
    await sess.close()


# --- Close ---


@requires_engine
async def test_session_close(container: AsyncContainer) -> None:
    sess = await container.session()
    await sess.send_and_wait("echo before close")
    await sess.close()
    # After close, container should still be functional
    result = await container.run("echo alive")
    assert result.ok


# --- Session + run() coexistence ---


@requires_engine
async def test_session_and_run_coexist(container: AsyncContainer) -> None:
    sess = await container.session()
    await sess.send_and_wait("export SESSION_VAR=yes")

    # run() uses a separate exec — should NOT see session's env
    run_result = await container.run("echo $SESSION_VAR")
    assert run_result.ok
    assert run_result.stdout.strip() == ""  # not set in run()'s exec

    # Session should still have the var
    sess_result = await sess.send_and_wait("echo $SESSION_VAR")
    assert sess_result.stdout.strip() == "yes"

    await sess.close()


# --- Shutdown cleans up sessions ---


@requires_engine
async def test_shutdown_cleans_sessions() -> None:
    c = await create_new_container()
    sess = await c.session()
    await sess.send_and_wait("echo setup")
    # Shutdown should close the session without error
    await c.shutdown()
