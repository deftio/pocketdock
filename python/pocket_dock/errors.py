# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

from __future__ import annotations


class PocketDockError(Exception):
    """Base exception for all pocket-dock errors."""


class SocketError(PocketDockError):
    """Error related to socket communication with the container engine."""


class SocketConnectionError(SocketError):
    """Cannot connect to the container engine socket."""

    def __init__(self, socket_path: str, detail: str = "") -> None:
        self.socket_path = socket_path
        msg = f"Cannot connect to socket at {socket_path}"
        if detail:
            msg = f"{msg}: {detail}"
        super().__init__(msg)


class SocketCommunicationError(SocketError):
    """Error during communication over the socket."""

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        msg = "Socket communication error"
        if detail:
            msg = f"{msg}: {detail}"
        super().__init__(msg)


class PodmanNotRunning(SocketError):
    """No container engine socket found."""

    def __init__(self) -> None:
        super().__init__(
            "No container engine socket found. "
            "Is Podman or Docker running? "
            "Try: systemctl --user start podman.socket"
        )


class ContainerError(PocketDockError):
    """Error related to a specific container."""

    def __init__(self, container_id: str, detail: str = "") -> None:
        self.container_id = container_id
        msg = f"Container {container_id}"
        if detail:
            msg = f"{msg}: {detail}"
        super().__init__(msg)


class ContainerNotFound(ContainerError):
    """Container does not exist (HTTP 404)."""

    def __init__(self, container_id: str) -> None:
        super().__init__(container_id, "not found")


class ContainerNotRunning(ContainerError):
    """Container exists but is not running (HTTP 409)."""

    def __init__(self, container_id: str) -> None:
        super().__init__(container_id, "is not running")


class ContainerGone(ContainerError):
    """Container was removed externally."""

    def __init__(self, container_id: str) -> None:
        super().__init__(container_id, "was removed externally")


class ImageNotFound(PocketDockError):
    """Requested image does not exist locally."""

    def __init__(self, image: str) -> None:
        self.image = image
        super().__init__(f"Image not found: {image}")


class SessionClosed(PocketDockError):
    """Operation attempted on a closed session."""


class ProjectNotInitialized(PocketDockError):
    """No .pocket-dock/ project directory found."""

    def __init__(self) -> None:
        super().__init__("No .pocket-dock/ project directory found. Run `pocket-dock init` first.")
