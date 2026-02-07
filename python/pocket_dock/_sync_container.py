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
from typing import TYPE_CHECKING

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

    from typing_extensions import Self

    from pocket_dock.types import ExecResult


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

    def run(
        self,
        command: str,
        *,
        timeout: float | None = None,
        max_output: int = _DEFAULT_MAX_OUTPUT,
        lang: str | None = None,
    ) -> ExecResult:
        """Execute a command inside the container and return the result.

        See :meth:`AsyncContainer.run` for full documentation.
        """
        return self._lt.run(  # type: ignore[return-value]
            self._ac.run(command, timeout=timeout, max_output=max_output, lang=lang),
        )

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


def create_new_container(
    *,
    image: str = _DEFAULT_IMAGE,
    name: str | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> Container:
    """Create and start a new container, returning a sync handle.

    See :func:`pocket_dock.async_.create_new_container` for argument docs.
    """
    lt = _LoopThread.get()
    ac = lt.run(_async_create(image=image, name=name, timeout=timeout))
    return Container(ac, lt)  # type: ignore[arg-type]
