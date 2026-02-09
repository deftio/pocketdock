"""Integration tests for streaming, detach, and callback features."""

from __future__ import annotations

import asyncio

from pocket_dock._async_container import create_new_container
from pocket_dock._process import AsyncExecStream, AsyncProcess
from pocket_dock.types import ExecResult

from .conftest import requires_engine

# --- run(stream=True) ---


@requires_engine
async def test_stream_echo() -> None:
    async with await create_new_container() as c:
        stream = await c.run("echo hello", stream=True)
        assert isinstance(stream, AsyncExecStream)
        chunks = [chunk async for chunk in stream]

        assert len(chunks) >= 1
        combined = "".join(ch.data for ch in chunks)
        assert "hello" in combined
        assert stream.result.exit_code == 0


@requires_engine
async def test_stream_stderr() -> None:
    async with await create_new_container() as c:
        chunks = [chunk async for chunk in await c.run("echo err >&2", stream=True)]

        stderr_chunks = [ch for ch in chunks if ch.stream == "stderr"]
        assert len(stderr_chunks) >= 1
        assert "err" in "".join(ch.data for ch in stderr_chunks)


@requires_engine
async def test_stream_mixed_output() -> None:
    async with await create_new_container() as c:
        stdout_data: list[str] = []
        stderr_data: list[str] = []
        async for chunk in await c.run("echo out && echo err >&2 && echo out2", stream=True):
            if chunk.stream == "stdout":
                stdout_data.append(chunk.data)
            else:
                stderr_data.append(chunk.data)

        assert "out" in "".join(stdout_data)
        assert "err" in "".join(stderr_data)


@requires_engine
async def test_stream_result_has_all_output() -> None:
    async with await create_new_container() as c:
        stream = await c.run("echo hello && echo world", stream=True)
        async for _ in stream:
            pass
        result = stream.result
        assert isinstance(result, ExecResult)
        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert "world" in result.stdout


@requires_engine
async def test_stream_long_output() -> None:
    async with await create_new_container() as c:
        stream = await c.run("seq 1 100", stream=True)
        total = ""
        async for chunk in stream:
            total += chunk.data
        assert "1\n" in total
        assert "100\n" in total


# --- run(detach=True) ---


@requires_engine
async def test_detach_basic() -> None:
    async with await create_new_container() as c:
        proc = await c.run("echo detached", detach=True)
        assert isinstance(proc, AsyncProcess)
        result = await proc.wait(timeout=10)
        assert result.exit_code == 0
        assert "detached" in result.stdout


@requires_engine
async def test_detach_is_running_and_wait() -> None:
    async with await create_new_container() as c:
        proc = await c.run("sleep 1 && echo done", detach=True)
        # Process should be running initially
        assert await proc.is_running() is True
        result = await proc.wait(timeout=10)
        assert result.exit_code == 0
        assert "done" in result.stdout
        assert await proc.is_running() is False


@requires_engine
async def test_detach_read_peek() -> None:
    async with await create_new_container() as c:
        proc = await c.run("echo hello", detach=True)
        await proc.wait(timeout=10)

        # peek doesn't drain
        snap1 = proc.peek()
        assert "hello" in snap1.stdout
        snap2 = proc.peek()
        assert snap2.stdout == snap1.stdout

        # read drains
        snap3 = proc.read()
        assert "hello" in snap3.stdout
        snap4 = proc.read()
        assert snap4.stdout == ""


@requires_engine
async def test_detach_kill() -> None:
    async with await create_new_container() as c:
        proc = await c.run("sleep 60", detach=True)
        # Give the process time to start
        await asyncio.sleep(0.5)
        assert await proc.is_running() is True
        # kill() sends the signal; shutdown() will cancel the read loop
        await proc.kill(signal=9)


# --- Callbacks ---


@requires_engine
async def test_callbacks_fire_on_detach() -> None:
    async with await create_new_container() as c:
        captured_stdout: list[str] = []
        captured_stderr: list[str] = []
        exit_codes: list[int] = []

        c.on_stdout(lambda _c, data: captured_stdout.append(data))
        c.on_stderr(lambda _c, data: captured_stderr.append(data))
        c.on_exit(lambda _c, code: exit_codes.append(code))

        proc = await c.run("echo cb_out && echo cb_err >&2", detach=True)
        await proc.wait(timeout=10)

        assert any("cb_out" in s for s in captured_stdout)
        assert any("cb_err" in s for s in captured_stderr)
        assert len(exit_codes) == 1
        assert exit_codes[0] == 0


@requires_engine
async def test_on_exit_fires_with_nonzero() -> None:
    async with await create_new_container() as c:
        exit_codes: list[int] = []
        c.on_exit(lambda _c, code: exit_codes.append(code))

        proc = await c.run("exit 42", detach=True)
        await proc.wait(timeout=10)

        assert exit_codes == [42]


# --- Shutdown cleanup ---


@requires_engine
async def test_shutdown_cleans_up_streams() -> None:
    c = await create_new_container()
    stream = await c.run("seq 1 10000", stream=True)
    # Don't iterate — shutdown should close cleanly
    await c.shutdown()
    # If we got here without hanging, cleanup worked
    assert stream is not None


@requires_engine
async def test_shutdown_cleans_up_detached() -> None:
    c = await create_new_container()
    proc = await c.run("sleep 60", detach=True)
    await asyncio.sleep(0.3)
    assert await proc.is_running() is True
    await c.shutdown()
    # Container is gone, process should be cancelled
    assert proc is not None


# --- stream + detach mutual exclusion ---


@requires_engine
async def test_stream_and_detach_raises() -> None:
    async with await create_new_container() as c:
        try:
            await c.run("echo x", stream=True, detach=True)
            msg = "Should have raised ValueError"
            raise AssertionError(msg)
        except ValueError:
            pass
