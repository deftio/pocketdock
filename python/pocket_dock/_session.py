# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Persistent shell session over a long-lived exec connection.

A :class:`AsyncSession` keeps a bash shell running inside the container.
Commands sent through the session share state (cwd, env vars, shell history)
because they all execute in the same shell process.

Command completion is detected via a sentinel protocol: each
:meth:`send_and_wait` appends ``echo __PD_{uuid}_${?}__`` after the user
command.  The background read loop scans stdout line-by-line for the
sentinel, extracts the exit code, and signals the waiting caller.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import threading
import time
import uuid
from typing import TYPE_CHECKING

from pocket_dock._stream import STREAM_STDOUT
from pocket_dock.errors import SessionClosed
from pocket_dock.types import ExecResult

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable

    from pocket_dock._logger import SessionLogHandle

_SENTINEL_RE = re.compile(r"__PD_(\w{16})_(\d+)__")


class _PendingCommand:
    """Internal state for a ``send_and_wait`` call in progress."""

    __slots__ = ("event", "exit_code", "start_time", "stderr", "stdout", "uuid")

    def __init__(self, cmd_uuid: str, event: asyncio.Event, start_time: float) -> None:
        self.uuid = cmd_uuid
        self.event = event
        self.start_time = start_time
        self.stdout: list[str] = []
        self.stderr: list[str] = []
        self.exit_code: int = -1


class AsyncSession:
    """Async handle to a persistent shell inside a container.

    Created via :meth:`AsyncContainer.session`.  Do not instantiate directly.
    """

    def __init__(  # noqa: PLR0913
        self,
        exec_id: str,
        frame_gen: AsyncGenerator[tuple[int, bytes], None],
        writer: asyncio.StreamWriter,
        socket_path: str,
        container_id: str,
        log_handle: SessionLogHandle | None = None,
    ) -> None:
        self._exec_id = exec_id
        self._frame_gen = frame_gen
        self._writer = writer
        self._socket_path = socket_path
        self._container_id = container_id
        self._log_handle = log_handle

        self._output: list[str] = []
        self._lock = threading.Lock()
        self._pending: _PendingCommand | None = None
        self._on_output_fns: list[Callable[..., object]] = []
        self._closed = False

        self._task = asyncio.ensure_future(self._read_loop())

    @property
    def id(self) -> str:
        """The exec instance ID backing this session."""
        return self._exec_id

    async def send(self, command: str) -> None:
        """Send a command to the shell without waiting for completion.

        The command's output will appear in :meth:`read` and trigger any
        :meth:`on_output` callbacks, but no sentinel is sent so the caller
        has no way to know when the command finishes.
        """
        if self._closed:
            raise SessionClosed
        if self._log_handle is not None:
            self._log_handle.write_send(command)
        self._writer.write(f"{command}\n".encode())
        await self._writer.drain()

    async def send_and_wait(
        self,
        command: str,
        *,
        timeout: float | None = None,
    ) -> ExecResult:
        """Send a command and wait for it to finish.

        A sentinel echo is appended after the command.  The background read
        loop detects the sentinel and extracts the exit code.

        Only one ``send_and_wait`` can be active at a time — the shell
        executes commands sequentially, so concurrent waits are a
        programming error.
        """
        if self._closed:
            raise SessionClosed
        if self._pending is not None:
            msg = "another send_and_wait is already pending"
            raise RuntimeError(msg)

        cmd_uuid = uuid.uuid4().hex[:16]
        pending = _PendingCommand(cmd_uuid, asyncio.Event(), time.monotonic())
        self._pending = pending

        # Send command followed by sentinel echo.
        # ${?} expands to the exit code of the preceding command.
        sentinel_cmd = f"echo __PD_{cmd_uuid}_${{?}}__"
        self._writer.write(f"{command}\n{sentinel_cmd}\n".encode())
        await self._writer.drain()

        try:
            if timeout is not None:
                await asyncio.wait_for(pending.event.wait(), timeout=timeout)
            else:
                await pending.event.wait()
        except (TimeoutError, asyncio.TimeoutError):
            return ExecResult(
                exit_code=-1,
                stdout="".join(pending.stdout),
                stderr="".join(pending.stderr),
                duration_ms=(time.monotonic() - pending.start_time) * 1000,
                timed_out=True,
            )
        finally:
            self._pending = None

        return ExecResult(
            exit_code=pending.exit_code,
            stdout="".join(pending.stdout),
            stderr="".join(pending.stderr),
            duration_ms=(time.monotonic() - pending.start_time) * 1000,
        )

    def read(self) -> str:
        """Drain and return all accumulated output (thread-safe)."""
        with self._lock:
            text = "".join(self._output)
            self._output.clear()
            return text

    def on_output(self, fn: Callable[..., object]) -> None:
        """Register a callback for output data.

        The callback receives a single ``str`` argument with the output text.
        Errors in callbacks are suppressed.
        """
        self._on_output_fns.append(fn)

    async def close(self) -> None:
        """Close the session, killing the shell process.

        Does **not** stop or remove the container — only the shell exec
        is terminated.
        """
        if self._closed:
            return
        self._closed = True
        if self._log_handle is not None:
            self._log_handle.close()
        self._writer.close()
        await self._writer.wait_closed()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    async def _close(self) -> None:
        """Clean up session resources, called by container shutdown."""
        await self.close()

    # ------------------------------------------------------------------
    # Background read loop
    # ------------------------------------------------------------------

    async def _read_loop(self) -> None:
        """Read frames from the exec stream, dispatch output and sentinels."""
        stdout_line_buf = ""
        try:
            async for stream_type, payload in self._frame_gen:
                text = payload.decode("utf-8", errors="replace")
                if stream_type == STREAM_STDOUT:
                    stdout_line_buf += text
                    while "\n" in stdout_line_buf:
                        line, stdout_line_buf = stdout_line_buf.split("\n", 1)
                        if self._check_sentinel(line):
                            continue
                        self._emit(line + "\n", is_stdout=True)
                else:
                    self._emit(text, is_stdout=False)
        finally:
            if self._pending is not None and not self._pending.event.is_set():
                self._pending.exit_code = -1
                self._pending.event.set()

    def _check_sentinel(self, line: str) -> bool:
        """Return True if *line* is a sentinel, consuming it."""
        match = _SENTINEL_RE.search(line)
        if match and self._pending and match.group(1) == self._pending.uuid:
            self._pending.exit_code = int(match.group(2))
            self._pending.event.set()
            return True
        return False

    def _emit(self, text: str, *, is_stdout: bool) -> None:
        """Dispatch output to the general buffer, pending command, and callbacks."""
        if self._log_handle is not None:
            self._log_handle.write_recv(text)
        with self._lock:
            self._output.append(text)
        if self._pending is not None and not self._pending.event.is_set():
            if is_stdout:
                self._pending.stdout.append(text)
            else:
                self._pending.stderr.append(text)
        for fn in self._on_output_fns:
            with contextlib.suppress(Exception):
                fn(text)
