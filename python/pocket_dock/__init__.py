# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

from __future__ import annotations

from importlib.metadata import version

from pocket_dock._buffer import BufferSnapshot
from pocket_dock._sync_container import (
    Container,
    SyncExecStream,
    SyncProcess,
    SyncSession,
    _LoopThread,
    create_new_container,
)
from pocket_dock.errors import (
    ContainerError,
    ContainerGone,
    ContainerNotFound,
    ContainerNotRunning,
    ImageNotFound,
    PocketDockError,
    PodmanNotRunning,
    SessionClosed,
    SocketCommunicationError,
    SocketConnectionError,
    SocketError,
)
from pocket_dock.persistence import (
    destroy_container as _async_destroy_container,
)
from pocket_dock.persistence import (
    list_containers as _async_list_containers,
)
from pocket_dock.persistence import (
    prune as _async_prune,
)
from pocket_dock.persistence import (
    resume_container as _async_resume_container,
)
from pocket_dock.types import ContainerInfo, ContainerListItem, ExecResult, StreamChunk

__version__ = version("pocket-dock")


def get_version() -> str:
    """Return the pocket-dock package version string."""
    return __version__


def resume_container(
    name: str,
    *,
    socket_path: str | None = None,
    timeout: int = 30,
) -> Container:
    """Resume a stopped persistent container by name (sync)."""
    lt = _LoopThread.get()
    ac = lt.run(_async_resume_container(name, socket_path=socket_path, timeout=timeout))
    return Container(ac, lt)  # type: ignore[arg-type]


def list_containers(
    *,
    socket_path: str | None = None,
) -> list[ContainerListItem]:
    """List all pocket-dock managed containers (sync)."""
    lt = _LoopThread.get()
    return lt.run(  # type: ignore[return-value]
        _async_list_containers(socket_path=socket_path)
    )


def destroy_container(
    name: str,
    *,
    socket_path: str | None = None,
) -> None:
    """Remove a container completely (sync)."""
    lt = _LoopThread.get()
    lt.run(_async_destroy_container(name, socket_path=socket_path))


def prune(
    *,
    socket_path: str | None = None,
) -> int:
    """Remove all stopped pocket-dock containers (sync)."""
    lt = _LoopThread.get()
    return lt.run(_async_prune(socket_path=socket_path))  # type: ignore[return-value]


ExecStream = SyncExecStream
Process = SyncProcess
Session = SyncSession

__all__ = [
    "BufferSnapshot",
    "Container",
    "ContainerError",
    "ContainerGone",
    "ContainerInfo",
    "ContainerListItem",
    "ContainerNotFound",
    "ContainerNotRunning",
    "ExecResult",
    "ExecStream",
    "ImageNotFound",
    "PocketDockError",
    "PodmanNotRunning",
    "Process",
    "Session",
    "SessionClosed",
    "SocketCommunicationError",
    "SocketConnectionError",
    "SocketError",
    "StreamChunk",
    "__version__",
    "create_new_container",
    "destroy_container",
    "get_version",
    "list_containers",
    "prune",
    "resume_container",
]
