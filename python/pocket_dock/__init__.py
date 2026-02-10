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
from pocket_dock.types import ContainerInfo, ExecResult, StreamChunk

__version__ = version("pocket-dock")


def get_version() -> str:
    """Return the pocket-dock package version string."""
    return __version__


ExecStream = SyncExecStream
Process = SyncProcess
Session = SyncSession

__all__ = [
    "BufferSnapshot",
    "Container",
    "ContainerError",
    "ContainerGone",
    "ContainerInfo",
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
    "get_version",
]
