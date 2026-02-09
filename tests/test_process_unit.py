"""Unit tests for AsyncExecStream and AsyncProcess."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

import pytest
from pocket_dock._callbacks import CallbackRegistry
from pocket_dock._process import AsyncExecStream, AsyncProcess
from pocket_dock._stream import STREAM_STDERR, STREAM_STDOUT
from pocket_dock.types import ExecResult, StreamChunk

# --- Helpers ---


async def _gen_from_list(
    items: list[tuple[int, bytes]],
) -> AsyncGenerator[tuple[int, bytes], None]:
    """Async generator yielding items from a list."""
    for item in items:
        yield item


def _mock_writer() -> MagicMock:
    writer = MagicMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    return writer


def _mock_container() -> MagicMock:
    c = MagicMock()
    c.socket_path = "/tmp/s.sock"
    c.container_id = "cid"
    return c


# --- AsyncExecStream ---


async def test_exec_stream_yields_chunks() -> None:
    frames = [(STREAM_STDOUT, b"hello\n"), (STREAM_STDERR, b"err\n")]
    writer = _mock_writer()

    with patch(
        "pocket_dock._socket_client._exec_inspect_exit_code",
        new_callable=AsyncMock,
        return_value=0,
    ):
        stream = AsyncExecStream("eid", _gen_from_list(frames), writer, "/tmp/s.sock", 0.0)
        chunks = [chunk async for chunk in stream]

    assert len(chunks) == 2
    assert chunks[0] == StreamChunk(stream="stdout", data="hello\n")
    assert chunks[1] == StreamChunk(stream="stderr", data="err\n")


async def test_exec_stream_result_after_iteration() -> None:
    frames = [(STREAM_STDOUT, b"out")]
    writer = _mock_writer()

    with patch(
        "pocket_dock._socket_client._exec_inspect_exit_code",
        new_callable=AsyncMock,
        return_value=0,
    ):
        stream = AsyncExecStream("eid", _gen_from_list(frames), writer, "/tmp/s.sock", 0.0)
        async for _ in stream:
            pass

    result = stream.result
    assert isinstance(result, ExecResult)
    assert result.exit_code == 0
    assert result.stdout == "out"


async def test_exec_stream_result_before_iteration_raises() -> None:
    writer = _mock_writer()
    stream = AsyncExecStream("eid", _gen_from_list([]), writer, "/tmp/s.sock", 0.0)
    with pytest.raises(RuntimeError, match="result not available"):
        _ = stream.result


async def test_exec_stream_close() -> None:
    writer = _mock_writer()
    stream = AsyncExecStream("eid", _gen_from_list([]), writer, "/tmp/s.sock", 0.0)
    await stream._close()
    writer.close.assert_called_once()
    writer.wait_closed.assert_awaited_once()


async def test_exec_stream_close_idempotent() -> None:
    writer = _mock_writer()
    stream = AsyncExecStream("eid", _gen_from_list([]), writer, "/tmp/s.sock", 0.0)
    await stream._close()
    await stream._close()  # second call is no-op
    writer.close.assert_called_once()


async def test_exec_stream_aiter_returns_self() -> None:
    writer = _mock_writer()
    stream = AsyncExecStream("eid", _gen_from_list([]), writer, "/tmp/s.sock", 0.0)
    assert stream.__aiter__() is stream


async def test_exec_stream_finalize_idempotent() -> None:
    """Finalize closes writer only once even if called twice."""
    frames = [(STREAM_STDOUT, b"x")]
    writer = _mock_writer()

    with patch(
        "pocket_dock._socket_client._exec_inspect_exit_code",
        new_callable=AsyncMock,
        return_value=0,
    ):
        stream = AsyncExecStream("eid", _gen_from_list(frames), writer, "/tmp/s.sock", 0.0)
        async for _ in stream:
            pass
        # Already finalized by iteration; calling again should be safe
        await stream._close()

    writer.close.assert_called_once()


async def test_exec_stream_close_before_iteration_ends() -> None:
    """_close() before iteration finishes makes _finalize a no-op."""
    frames = [(STREAM_STDOUT, b"x")]
    writer = _mock_writer()

    stream = AsyncExecStream("eid", _gen_from_list(frames), writer, "/tmp/s.sock", 0.0)
    # Close before iterating
    await stream._close()

    # Now iterate — finalize should be a no-op (line 73 coverage)
    with patch(
        "pocket_dock._socket_client._exec_inspect_exit_code",
        new_callable=AsyncMock,
        return_value=0,
    ):
        chunks = [chunk async for chunk in stream]

    assert len(chunks) == 1
    # result is not set because _finalize was skipped
    with pytest.raises(RuntimeError, match="result not available"):
        _ = stream.result


# --- AsyncProcess ---


async def test_process_id() -> None:
    container = _mock_container()
    writer = _mock_writer()
    callbacks = CallbackRegistry()

    with patch(
        "pocket_dock._socket_client._exec_inspect_exit_code",
        new_callable=AsyncMock,
        return_value=0,
    ):
        proc = AsyncProcess("exec-123", container, _gen_from_list([]), writer, callbacks)
        assert proc.id == "exec-123"
        await proc.wait()


async def test_process_read_peek() -> None:
    container = _mock_container()
    writer = _mock_writer()
    callbacks = CallbackRegistry()
    frames = [(STREAM_STDOUT, b"hello")]

    with patch(
        "pocket_dock._socket_client._exec_inspect_exit_code",
        new_callable=AsyncMock,
        return_value=0,
    ):
        proc = AsyncProcess("eid", container, _gen_from_list(frames), writer, callbacks)
        await proc.wait()

    # peek doesn't drain
    snap = proc.peek()
    assert snap.stdout == "hello"
    snap2 = proc.peek()
    assert snap2.stdout == "hello"

    # read drains
    snap3 = proc.read()
    assert snap3.stdout == "hello"
    snap4 = proc.read()
    assert snap4.stdout == ""


async def test_process_is_running() -> None:
    container = _mock_container()
    writer = _mock_writer()
    callbacks = CallbackRegistry()
    frames = [(STREAM_STDOUT, b"x")]

    with patch(
        "pocket_dock._socket_client._exec_inspect_exit_code",
        new_callable=AsyncMock,
        return_value=0,
    ):
        proc = AsyncProcess("eid", container, _gen_from_list(frames), writer, callbacks)
        # Wait for background task to complete
        await proc.wait()

    assert await proc.is_running() is False


async def test_process_wait_returns_exec_result() -> None:
    container = _mock_container()
    writer = _mock_writer()
    callbacks = CallbackRegistry()
    frames = [(STREAM_STDOUT, b"output"), (STREAM_STDERR, b"err")]

    with patch(
        "pocket_dock._socket_client._exec_inspect_exit_code",
        new_callable=AsyncMock,
        return_value=42,
    ):
        proc = AsyncProcess("eid", container, _gen_from_list(frames), writer, callbacks)
        result = await proc.wait()

    assert result.exit_code == 42
    assert result.stdout == "output"
    assert result.stderr == "err"


async def test_process_buffer_size_and_overflow() -> None:
    container = _mock_container()
    writer = _mock_writer()
    callbacks = CallbackRegistry()
    frames = [(STREAM_STDOUT, b"x" * 100)]

    with patch(
        "pocket_dock._socket_client._exec_inspect_exit_code",
        new_callable=AsyncMock,
        return_value=0,
    ):
        proc = AsyncProcess(
            "eid",
            container,
            _gen_from_list(frames),
            writer,
            callbacks,
            buffer_capacity=50,  # force overflow
        )
        await proc.wait()

    assert proc.buffer_overflow is True
    assert proc.buffer_size <= 50


async def test_process_callbacks_fire() -> None:
    container = _mock_container()
    writer = _mock_writer()
    callbacks = CallbackRegistry()
    captured: list[tuple[str, object]] = []
    callbacks.on_stdout(lambda _c, d: captured.append(("stdout", d)))
    callbacks.on_stderr(lambda _c, d: captured.append(("stderr", d)))
    exit_codes: list[int] = []
    callbacks.on_exit(lambda _c, code: exit_codes.append(code))

    frames = [(STREAM_STDOUT, b"out"), (STREAM_STDERR, b"err")]

    with patch(
        "pocket_dock._socket_client._exec_inspect_exit_code",
        new_callable=AsyncMock,
        return_value=0,
    ):
        proc = AsyncProcess("eid", container, _gen_from_list(frames), writer, callbacks)
        await proc.wait()

    assert ("stdout", "out") in captured
    assert ("stderr", "err") in captured
    assert exit_codes == [0]


async def test_process_cancel() -> None:
    container = _mock_container()
    writer = _mock_writer()
    callbacks = CallbackRegistry()

    with patch(
        "pocket_dock._socket_client._exec_inspect_exit_code",
        new_callable=AsyncMock,
        return_value=0,
    ):
        proc = AsyncProcess("eid", container, _gen_from_list([]), writer, callbacks)
        await proc.wait()
        await proc._cancel()
        # Task is already done; cancel should be a no-op


async def test_process_kill() -> None:
    container = _mock_container()
    writer = _mock_writer()
    callbacks = CallbackRegistry()

    # Create a slow generator to keep process alive
    async def slow_gen() -> AsyncGenerator[tuple[int, bytes], None]:
        yield (STREAM_STDOUT, b"start")
        await asyncio.sleep(10)

    with (
        patch(
            "pocket_dock._socket_client._exec_inspect_exit_code",
            new_callable=AsyncMock,
            return_value=-1,
        ),
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(200, b'{"Pid": 42}'),
        ),
        patch(
            "pocket_dock._socket_client.exec_command",
            new_callable=AsyncMock,
        ) as mock_exec,
    ):
        proc = AsyncProcess("eid", container, slow_gen(), writer, callbacks)
        # Give the read loop time to start
        await asyncio.sleep(0.05)
        assert await proc.is_running() is True

        await proc.kill(signal=9)
        mock_exec.assert_awaited_once()
        call_args = mock_exec.call_args[0]
        assert call_args[2] == ["kill", "-9", "42"]

        await proc._cancel()


async def test_process_kill_already_done() -> None:
    container = _mock_container()
    writer = _mock_writer()
    callbacks = CallbackRegistry()

    with patch(
        "pocket_dock._socket_client._exec_inspect_exit_code",
        new_callable=AsyncMock,
        return_value=0,
    ):
        proc = AsyncProcess("eid", container, _gen_from_list([]), writer, callbacks)
        await proc.wait()
        # Kill on already-finished process should be no-op
        await proc.kill()


async def test_process_kill_inspect_error() -> None:
    container = _mock_container()
    writer = _mock_writer()
    callbacks = CallbackRegistry()

    async def slow_gen() -> AsyncGenerator[tuple[int, bytes], None]:
        yield (STREAM_STDOUT, b"x")
        await asyncio.sleep(10)

    with (
        patch(
            "pocket_dock._socket_client._exec_inspect_exit_code",
            new_callable=AsyncMock,
            return_value=-1,
        ),
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(500, b"error"),
        ),
    ):
        proc = AsyncProcess("eid", container, slow_gen(), writer, callbacks)
        await asyncio.sleep(0.05)
        # Should not raise even if inspect fails
        await proc.kill()
        await proc._cancel()


async def test_process_kill_pid_zero() -> None:
    """kill() does nothing when exec inspect returns pid=0."""
    container = _mock_container()
    writer = _mock_writer()
    callbacks = CallbackRegistry()

    async def slow_gen() -> AsyncGenerator[tuple[int, bytes], None]:
        yield (STREAM_STDOUT, b"x")
        await asyncio.sleep(10)

    with (
        patch(
            "pocket_dock._socket_client._exec_inspect_exit_code",
            new_callable=AsyncMock,
            return_value=-1,
        ),
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(200, b'{"Pid": 0}'),
        ),
        patch(
            "pocket_dock._socket_client.exec_command",
            new_callable=AsyncMock,
        ) as mock_exec,
    ):
        proc = AsyncProcess("eid", container, slow_gen(), writer, callbacks)
        await asyncio.sleep(0.05)
        await proc.kill()
        # exec_command should NOT have been called since pid=0
        mock_exec.assert_not_awaited()
        await proc._cancel()


async def test_process_wait_with_timeout() -> None:
    container = _mock_container()
    writer = _mock_writer()
    callbacks = CallbackRegistry()

    with patch(
        "pocket_dock._socket_client._exec_inspect_exit_code",
        new_callable=AsyncMock,
        return_value=0,
    ):
        proc = AsyncProcess(
            "eid", container, _gen_from_list([(STREAM_STDOUT, b"ok")]), writer, callbacks
        )
        result = await proc.wait(timeout=5.0)
    assert result.exit_code == 0
