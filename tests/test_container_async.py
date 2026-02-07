"""Integration tests for AsyncContainer (async core)."""

from __future__ import annotations

import asyncio

from pocket_dock._async_container import AsyncContainer, create_new_container
from pocket_dock.types import ExecResult

from .conftest import requires_engine

# --- Factory & lifecycle ---


@requires_engine
async def test_create_and_shutdown() -> None:
    c = await create_new_container()
    assert isinstance(c, AsyncContainer)
    assert c.container_id
    assert c.name.startswith("pd-")
    await c.shutdown()


@requires_engine
async def test_create_custom_name() -> None:
    c = await create_new_container(name="pd-testcustom")
    assert c.name == "pd-testcustom"
    await c.shutdown()


@requires_engine
async def test_context_manager() -> None:
    async with await create_new_container() as c:
        result = await c.run("echo hello")
        assert result.ok


# --- run() basics ---


@requires_engine
async def test_run_echo() -> None:
    async with await create_new_container() as c:
        result = await c.run("echo hello")
        assert isinstance(result, ExecResult)
        assert result.ok
        assert result.exit_code == 0
        assert result.stdout.strip() == "hello"
        assert result.stderr == ""
        assert result.duration_ms > 0


@requires_engine
async def test_run_stderr() -> None:
    async with await create_new_container() as c:
        result = await c.run("echo err >&2")
        assert result.ok
        assert result.stderr.strip() == "err"


@requires_engine
async def test_run_nonzero_exit() -> None:
    async with await create_new_container() as c:
        result = await c.run("exit 42")
        assert not result.ok
        assert result.exit_code == 42


@requires_engine
async def test_run_python() -> None:
    async with await create_new_container() as c:
        result = await c.run("print(1 + 2)", lang="python")
        assert result.ok
        assert result.stdout.strip() == "3"


@requires_engine
async def test_run_python_multiline() -> None:
    code = "import sys\nprint(sys.version_info.major)"
    async with await create_new_container() as c:
        result = await c.run(code, lang="python")
        assert result.ok
        assert result.stdout.strip() == "3"


# --- Timeout ---


@requires_engine
async def test_run_timeout() -> None:
    async with await create_new_container() as c:
        result = await c.run("sleep 60", timeout=1)
        assert not result.ok
        assert result.timed_out
        assert result.exit_code == -1
        assert result.duration_ms >= 900


# --- Output capping ---


@requires_engine
async def test_run_output_truncation() -> None:
    async with await create_new_container() as c:
        result = await c.run(
            "python3 -c \"print('x' * 10000)\"",
            max_output=1024,
        )
        assert result.truncated


# --- Sequential and concurrent exec ---


@requires_engine
async def test_sequential_runs() -> None:
    async with await create_new_container() as c:
        r1 = await c.run("echo first")
        r2 = await c.run("echo second")
        assert r1.stdout.strip() == "first"
        assert r2.stdout.strip() == "second"


@requires_engine
async def test_concurrent_runs() -> None:
    async with await create_new_container() as c:
        r1, r2 = await asyncio.gather(
            c.run("echo alpha"),
            c.run("echo bravo"),
        )
        assert r1.ok
        assert r2.ok
        assert {r1.stdout.strip(), r2.stdout.strip()} == {"alpha", "bravo"}


# --- Shutdown idempotency ---


@requires_engine
async def test_shutdown_idempotent() -> None:
    c = await create_new_container()
    await c.shutdown()
    await c.shutdown()  # second call is no-op


@requires_engine
async def test_shutdown_force() -> None:
    c = await create_new_container()
    await c.shutdown(force=True)
