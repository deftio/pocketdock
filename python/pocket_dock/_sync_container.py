# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Sync facade over :class:`AsyncContainer`.

Manages a background event loop thread so users never see ``async/await``
unless they want to.  Thread-safe by construction — each call dispatches
to the background event loop via :func:`asyncio.run_coroutine_threadsafe`.
"""

from __future__ import annotations

import asyncio
import atexit
import threading
from typing import TYPE_CHECKING, Literal, overload

from pocket_dock._async_container import (
    _DEFAULT_IMAGE,
    _DEFAULT_MAX_OUTPUT,
    _DEFAULT_TIMEOUT,
    AsyncContainer,
)
from pocket_dock._async_container import (
    create_new_container as _async_create,
)

if TYPE_CHECKING:
    import concurrent.futures
    from collections.abc import Callable

    from typing_extensions import Self

    from pocket_dock._buffer import BufferSnapshot
    from pocket_dock._process import AsyncExecStream, AsyncProcess
    from pocket_dock._session import AsyncSession
    from pocket_dock.types import ContainerInfo, ExecResult, StreamChunk


class _LoopThread:
    """Singleton background event loop thread shared by all sync Containers."""

    _instance: _LoopThread | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever,
            name="pocket-dock-event-loop",
            daemon=True,
        )
        self._thread.start()
        atexit.register(self._shutdown)

    @classmethod
    def get(cls) -> _LoopThread:
        """Return the singleton, creating it lazily."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return self._loop

    def run(self, coro: object, *, timeout: float | None = None) -> object:
        """Submit a coroutine and block until it finishes."""
        future: concurrent.futures.Future[object] = asyncio.run_coroutine_threadsafe(
            coro,  # type: ignore[arg-type]
            self._loop,
        )
        return future.result(timeout=timeout)

    def _shutdown(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)


class SyncExecStream:
    """Sync iterator over streaming exec output.

    Wraps :class:`AsyncExecStream` for synchronous usage.
    """

    def __init__(self, async_stream: AsyncExecStream, lt: _LoopThread) -> None:
        self._async_stream = async_stream
        self._lt = lt

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> StreamChunk:
        try:
            return self._lt.run(self._async_stream.__anext__())  # type: ignore[return-value]
        except StopAsyncIteration:
            raise StopIteration from None

    @property
    def result(self) -> ExecResult:
        """Return the ExecResult (only available after iteration completes)."""
        return self._async_stream.result


class SyncProcess:
    """Sync handle to a detached exec process.

    Wraps :class:`AsyncProcess` for synchronous usage.
    """

    def __init__(self, async_process: AsyncProcess, lt: _LoopThread) -> None:
        self._async_process = async_process
        self._lt = lt

    @property
    def id(self) -> str:
        """The exec instance ID."""
        return self._async_process.id

    def is_running(self) -> bool:
        """Return True if the background process is still running."""
        return self._lt.run(self._async_process.is_running())  # type: ignore[return-value]

    def kill(self, signal: int = 15) -> None:
        """Kill the exec process by sending a signal."""
        self._lt.run(self._async_process.kill(signal=signal))

    def read(self) -> BufferSnapshot:
        """Drain and return all buffered output."""
        return self._async_process.read()

    def peek(self) -> BufferSnapshot:
        """Return buffered output without draining."""
        return self._async_process.peek()

    def wait(self, timeout: float | None = None) -> ExecResult:
        """Block until the process exits, then return ExecResult."""
        return self._lt.run(  # type: ignore[return-value]
            self._async_process.wait(timeout=timeout),
        )

    @property
    def buffer_size(self) -> int:
        """Current bytes in the ring buffer."""
        return self._async_process.buffer_size

    @property
    def buffer_overflow(self) -> bool:
        """True if any buffered data was evicted due to capacity."""
        return self._async_process.buffer_overflow


class SyncSession:
    """Sync handle to a persistent shell session.

    Wraps :class:`AsyncSession` for synchronous usage.
    """

    def __init__(self, async_session: AsyncSession, lt: _LoopThread) -> None:
        self._async_session = async_session
        self._lt = lt

    @property
    def id(self) -> str:
        """The exec instance ID backing this session."""
        return self._async_session.id

    def send(self, command: str) -> None:
        """Send a command to the shell without waiting for completion."""
        self._lt.run(self._async_session.send(command))

    def send_and_wait(self, command: str, *, timeout: float | None = None) -> ExecResult:
        """Send a command and wait for it to finish."""
        return self._lt.run(  # type: ignore[return-value]
            self._async_session.send_and_wait(command, timeout=timeout),
        )

    def read(self) -> str:
        """Drain and return all accumulated output (thread-safe)."""
        return self._async_session.read()

    def on_output(self, fn: Callable[..., object]) -> None:
        """Register a callback for output data."""
        self._async_session.on_output(fn)

    def close(self) -> None:
        """Close the session, killing the shell process."""
        self._lt.run(self._async_session.close())


class Container:
    """Sync handle to a running container.

    Created via :func:`pocket_dock.create_new_container`.
    Do not instantiate directly.
    """

    def __init__(self, ac: AsyncContainer, lt: _LoopThread) -> None:
        self._ac = ac
        self._lt = lt

    @property
    def container_id(self) -> str:
        """Full container ID hex string."""
        return self._ac.container_id

    @property
    def socket_path(self) -> str:
        """Path to the container engine Unix socket."""
        return self._ac.socket_path

    @property
    def name(self) -> str:
        """Human-readable container name (e.g. ``pd-a1b2c3d4``)."""
        return self._ac.name

    @property
    def persist(self) -> bool:
        """Whether this container survives shutdown (stop without remove)."""
        return self._ac.persist

    @property
    def project(self) -> str:
        """Project name this container belongs to (empty if none)."""
        return self._ac.project

    @property
    def data_path(self) -> str:
        """Instance data directory path (empty if none)."""
        return self._ac.data_path

    @overload
    def run(
        self,
        command: str,
        *,
        stream: Literal[True],
        timeout: float | None = ...,
        max_output: int = ...,
        lang: str | None = ...,
    ) -> SyncExecStream: ...

    @overload
    def run(
        self,
        command: str,
        *,
        detach: Literal[True],
        timeout: float | None = ...,
        max_output: int = ...,
        lang: str | None = ...,
    ) -> SyncProcess: ...

    @overload
    def run(
        self,
        command: str,
        *,
        timeout: float | None = ...,
        max_output: int = ...,
        lang: str | None = ...,
    ) -> ExecResult: ...

    @overload
    def run(
        self,
        command: str,
        *,
        stream: bool,
        detach: bool,
        timeout: float | None = ...,
        max_output: int = ...,
        lang: str | None = ...,
    ) -> ExecResult | SyncExecStream | SyncProcess: ...

    def run(  # noqa: PLR0913
        self,
        command: str,
        *,
        stream: bool = False,
        detach: bool = False,
        timeout: float | None = None,
        max_output: int = _DEFAULT_MAX_OUTPUT,
        lang: str | None = None,
    ) -> ExecResult | SyncExecStream | SyncProcess:
        """Execute a command inside the container.

        See :meth:`AsyncContainer.run` for full documentation.
        """
        result = self._lt.run(
            self._ac.run(
                command,
                stream=stream,
                detach=detach,
                timeout=timeout,
                max_output=max_output,
                lang=lang,
            ),
        )
        if stream:
            return SyncExecStream(result, self._lt)  # type: ignore[arg-type]
        if detach:
            return SyncProcess(result, self._lt)  # type: ignore[arg-type]
        return result  # type: ignore[return-value]

    def info(self) -> ContainerInfo:
        """Return a live snapshot of the container's state and resource usage.

        See :meth:`AsyncContainer.info` for full documentation.
        """
        return self._lt.run(self._ac.info())  # type: ignore[return-value]

    def reboot(self, *, fresh: bool = False) -> None:
        """Restart the container.

        See :meth:`AsyncContainer.reboot` for full documentation.
        """
        self._lt.run(self._ac.reboot(fresh=fresh))

    def write_file(self, path: str, content: str | bytes) -> None:
        """Write a file into the container.

        See :meth:`AsyncContainer.write_file` for full documentation.
        """
        self._lt.run(self._ac.write_file(path, content))

    def read_file(self, path: str) -> bytes:
        """Read a file from the container.

        See :meth:`AsyncContainer.read_file` for full documentation.
        """
        return self._lt.run(self._ac.read_file(path))  # type: ignore[return-value]

    def list_files(self, path: str = "/home/sandbox") -> list[str]:
        """List directory contents inside the container.

        See :meth:`AsyncContainer.list_files` for full documentation.
        """
        return self._lt.run(self._ac.list_files(path))  # type: ignore[return-value]

    def push(self, src: str, dest: str) -> None:
        """Copy a file or directory from the host into the container.

        See :meth:`AsyncContainer.push` for full documentation.
        """
        self._lt.run(self._ac.push(src, dest))

    def pull(self, src: str, dest: str) -> None:
        """Copy a file or directory from the container to the host.

        See :meth:`AsyncContainer.pull` for full documentation.
        """
        self._lt.run(self._ac.pull(src, dest))

    def on_stdout(self, fn: Callable[..., object]) -> None:
        """Register a callback for stdout data from detached processes."""
        self._ac.on_stdout(fn)

    def on_stderr(self, fn: Callable[..., object]) -> None:
        """Register a callback for stderr data from detached processes."""
        self._ac.on_stderr(fn)

    def on_exit(self, fn: Callable[..., object]) -> None:
        """Register a callback for process exit from detached processes."""
        self._ac.on_exit(fn)

    def session(self) -> SyncSession:
        """Open a persistent shell session inside the container.

        See :meth:`AsyncContainer.session` for full documentation.
        """
        async_session = self._lt.run(self._ac.session())
        return SyncSession(async_session, self._lt)  # type: ignore[arg-type]

    def snapshot(self, image_name: str) -> str:
        """Commit the container's current filesystem as a new image.

        See :meth:`AsyncContainer.snapshot` for full documentation.
        """
        return self._lt.run(self._ac.snapshot(image_name))  # type: ignore[return-value]

    def shutdown(self, *, force: bool = False) -> None:
        """Stop and remove the container.

        See :meth:`AsyncContainer.shutdown` for full documentation.
        """
        self._lt.run(self._ac.shutdown(force=force))

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self.shutdown()


def create_new_container(  # noqa: PLR0913
    *,
    image: str = _DEFAULT_IMAGE,
    name: str | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
    mem_limit: str | None = None,
    cpu_percent: int | None = None,
    persist: bool = False,
    volumes: dict[str, str] | None = None,
    project: str | None = None,
) -> Container:
    """Create and start a new container, returning a sync handle.

    See :func:`pocket_dock.async_.create_new_container` for argument docs.
    """
    lt = _LoopThread.get()
    ac = lt.run(
        _async_create(
            image=image,
            name=name,
            timeout=timeout,
            mem_limit=mem_limit,
            cpu_percent=cpu_percent,
            persist=persist,
            volumes=volumes,
            project=project,
        )
    )
    return Container(ac, lt)  # type: ignore[arg-type]
