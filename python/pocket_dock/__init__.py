# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

from __future__ import annotations

from importlib.metadata import version

from pocket_dock._buffer import BufferSnapshot
from pocket_dock._sync_container import Container, create_new_container
from pocket_dock.errors import (
    ContainerError,
    ContainerGone,
    ContainerNotFound,
    ContainerNotRunning,
    ImageNotFound,
    PocketDockError,
    PodmanNotRunning,
    SocketCommunicationError,
    SocketConnectionError,
    SocketError,
)
from pocket_dock.types import ContainerInfo, ExecResult, StreamChunk

__version__ = version("pocket-dock")


def get_version() -> str:
    """Return the pocket-dock package version string."""
    return __version__


__all__ = [
    "BufferSnapshot",
    "Container",
    "ContainerError",
    "ContainerGone",
    "ContainerInfo",
    "ContainerNotFound",
    "ContainerNotRunning",
    "ExecResult",
    "ImageNotFound",
    "PocketDockError",
    "PodmanNotRunning",
    "SocketCommunicationError",
    "SocketConnectionError",
    "SocketError",
    "StreamChunk",
    "__version__",
    "create_new_container",
    "get_version",
]
