# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Detached process handle and streaming exec iterator."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import TYPE_CHECKING

from pocket_dock._buffer import BufferSnapshot, RingBuffer
from pocket_dock._stream import STREAM_STDOUT
from pocket_dock.types import ExecResult, StreamChunk

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from typing_extensions import Self

    from pocket_dock._async_container import AsyncContainer
    from pocket_dock._callbacks import CallbackRegistry


class AsyncExecStream:
    """Async iterator over streaming exec output.

    Returned by ``AsyncContainer.run(stream=True)``.  Yields ``StreamChunk``
    objects as output arrives.  After iteration completes, the ``result``
    property provides the finalized ``ExecResult``.
    """

    def __init__(
        self,
        exec_id: str,
        frame_gen: AsyncGenerator[tuple[int, bytes], None],
        writer: asyncio.StreamWriter,
        socket_path: str,
        start_time: float,
    ) -> None:
        self._exec_id = exec_id
        self._frame_gen = frame_gen
        self._writer = writer
        self._socket_path = socket_path
        self._start_time = start_time
        self._result: ExecResult | None = None
        self._stdout_parts: list[str] = []
        self._stderr_parts: list[str] = []
        self._closed = False

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> StreamChunk:
        try:
            stream_type, payload = await self._frame_gen.__anext__()
        except StopAsyncIteration:
            await self._finalize()
            raise

        data = payload.decode("utf-8", errors="replace")
        if stream_type == STREAM_STDOUT:
            self._stdout_parts.append(data)
            return StreamChunk(stream="stdout", data=data)
        self._stderr_parts.append(data)
        return StreamChunk(stream="stderr", data=data)

    async def _finalize(self) -> None:
        """Close connection and build ExecResult."""
        if self._closed:
            return
        self._closed = True
        self._writer.close()
        await self._writer.wait_closed()

        from pocket_dock._socket_client import _exec_inspect_exit_code  # noqa: PLC0415

        exit_code = await _exec_inspect_exit_code(self._socket_path, self._exec_id)
        duration_ms = (time.monotonic() - self._start_time) * 1000

        self._result = ExecResult(
            exit_code=exit_code,
            stdout="".join(self._stdout_parts),
            stderr="".join(self._stderr_parts),
            duration_ms=duration_ms,
        )

    @property
    def result(self) -> ExecResult:
        """Return the ExecResult (only available after iteration completes)."""
        if self._result is None:
            msg = "result not available until iteration completes"
            raise RuntimeError(msg)
        return self._result

    async def _close(self) -> None:
        """Close the stream connection.  Used by shutdown()."""
        if self._closed:
            return
        self._closed = True
        self._writer.close()
        await self._writer.wait_closed()


class AsyncProcess:
    """Handle to a detached exec process running in a container.

    Returned by ``AsyncContainer.run(detach=True)``.  A background task reads
    the exec stream and dispatches frames to the ring buffer and callbacks.
    """

    def __init__(  # noqa: PLR0913
        self,
        exec_id: str,
        container: AsyncContainer,
        frame_gen: AsyncGenerator[tuple[int, bytes], None],
        writer: asyncio.StreamWriter,
        callbacks: CallbackRegistry,
        buffer_capacity: int = 1_048_576,
    ) -> None:
        self._exec_id = exec_id
        self._container = container
        self._socket_path = container.socket_path
        self._writer = writer
        self._callbacks = callbacks
        self._buffer = RingBuffer(buffer_capacity)
        self._done = asyncio.Event()
        self._exit_code: int = -1
        self._task = asyncio.get_running_loop().create_task(self._read_loop(frame_gen))

    async def _read_loop(
        self,
        gen: AsyncGenerator[tuple[int, bytes], None],
    ) -> None:
        """Background task: read frames, dispatch to buffer and callbacks."""
        try:
            async for stream_type, payload in gen:
                self._buffer.write(stream_type, payload)
                data_str = payload.decode("utf-8", errors="replace")
                if stream_type == STREAM_STDOUT:
                    self._callbacks.dispatch_stdout(self._container, data_str)
                else:
                    self._callbacks.dispatch_stderr(self._container, data_str)
        finally:
            self._writer.close()
            await self._writer.wait_closed()

            from pocket_dock._socket_client import _exec_inspect_exit_code  # noqa: PLC0415

            with contextlib.suppress(Exception):
                self._exit_code = await _exec_inspect_exit_code(self._socket_path, self._exec_id)

            self._done.set()
            self._callbacks.dispatch_exit(self._container, self._exit_code)

    @property
    def id(self) -> str:
        """The exec instance ID."""
        return self._exec_id

    async def is_running(self) -> bool:
        """Return True if the background process is still running."""
        return not self._done.is_set()

    async def kill(self, signal: int = 15) -> None:
        """Kill the exec process by sending a signal.

        Inspects the exec to get its PID, then runs ``kill`` inside the
        container.  Default signal is SIGTERM (15).
        """
        if self._done.is_set():
            return

        from pocket_dock._socket_client import _request, exec_command  # noqa: PLC0415

        status, body = await _request(self._socket_path, "GET", f"/exec/{self._exec_id}/json")
        if status >= 400:  # noqa: PLR2004
            return
        data = json.loads(body)
        pid = data.get("Pid", 0)
        if pid > 0:
            with contextlib.suppress(Exception):
                await exec_command(
                    self._socket_path,
                    self._container.container_id,
                    ["kill", f"-{signal}", str(pid)],
                    timeout=5,
                )

    def read(self) -> BufferSnapshot:
        """Drain and return all buffered output."""
        return self._buffer.read()

    def peek(self) -> BufferSnapshot:
        """Return buffered output without draining."""
        return self._buffer.peek()

    async def wait(self, timeout: float | None = None) -> ExecResult:
        """Block until the process exits, then return ExecResult."""
        if timeout is not None:
            await asyncio.wait_for(self._done.wait(), timeout=timeout)
        else:
            await self._done.wait()
        snapshot = self._buffer.peek()
        return ExecResult(
            exit_code=self._exit_code,
            stdout=snapshot.stdout,
            stderr=snapshot.stderr,
        )

    @property
    def buffer_size(self) -> int:
        """Current bytes in the ring buffer."""
        return self._buffer.size

    @property
    def buffer_overflow(self) -> bool:
        """True if any buffered data was evicted due to capacity."""
        return self._buffer.overflow

    async def _cancel(self) -> None:
        """Cancel the background task.  Used by shutdown()."""
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
