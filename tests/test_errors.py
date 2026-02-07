"""Tests for the pocket-dock error hierarchy."""

from __future__ import annotations

import pocket_dock
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

# -- Inheritance --


def test_socket_error_is_pocket_dock_error() -> None:
    assert issubclass(SocketError, PocketDockError)


def test_socket_connection_error_is_socket_error() -> None:
    assert issubclass(SocketConnectionError, SocketError)


def test_socket_communication_error_is_socket_error() -> None:
    assert issubclass(SocketCommunicationError, SocketError)


def test_podman_not_running_is_socket_error() -> None:
    assert issubclass(PodmanNotRunning, SocketError)


def test_container_error_is_pocket_dock_error() -> None:
    assert issubclass(ContainerError, PocketDockError)


def test_container_not_found_is_container_error() -> None:
    assert issubclass(ContainerNotFound, ContainerError)


def test_container_not_running_is_container_error() -> None:
    assert issubclass(ContainerNotRunning, ContainerError)


def test_container_gone_is_container_error() -> None:
    assert issubclass(ContainerGone, ContainerError)


def test_image_not_found_is_pocket_dock_error() -> None:
    assert issubclass(ImageNotFound, PocketDockError)


# -- Catchability --


def test_catch_socket_connection_error_as_pocket_dock_error() -> None:
    try:
        raise SocketConnectionError("/tmp/test.sock")
    except PocketDockError:
        pass


def test_catch_container_not_found_as_container_error() -> None:
    try:
        raise ContainerNotFound("abc123")
    except ContainerError:
        pass


def test_catch_image_not_found_as_pocket_dock_error() -> None:
    try:
        raise ImageNotFound("missing:latest")
    except PocketDockError:
        pass


# -- Attribute storage --


def test_socket_connection_error_stores_path() -> None:
    err = SocketConnectionError("/tmp/test.sock", "refused")
    assert err.socket_path == "/tmp/test.sock"
    assert "refused" in str(err)
    assert "/tmp/test.sock" in str(err)


def test_socket_connection_error_without_detail() -> None:
    err = SocketConnectionError("/tmp/test.sock")
    assert err.socket_path == "/tmp/test.sock"
    assert str(err) == "Cannot connect to socket at /tmp/test.sock"


def test_socket_communication_error_stores_detail() -> None:
    err = SocketCommunicationError("broken pipe")
    assert err.detail == "broken pipe"
    assert "broken pipe" in str(err)


def test_socket_communication_error_without_detail() -> None:
    err = SocketCommunicationError()
    assert str(err) == "Socket communication error"


def test_podman_not_running_message() -> None:
    err = PodmanNotRunning()
    assert "Podman" in str(err)
    assert "systemctl" in str(err)


def test_container_error_stores_id() -> None:
    err = ContainerError("abc123", "something wrong")
    assert err.container_id == "abc123"
    assert "abc123" in str(err)
    assert "something wrong" in str(err)


def test_container_error_without_detail() -> None:
    err = ContainerError("abc123")
    assert str(err) == "Container abc123"


def test_container_not_found_message() -> None:
    err = ContainerNotFound("abc123")
    assert err.container_id == "abc123"
    assert "not found" in str(err)


def test_container_not_running_message() -> None:
    err = ContainerNotRunning("abc123")
    assert err.container_id == "abc123"
    assert "not running" in str(err)


def test_container_gone_message() -> None:
    err = ContainerGone("abc123")
    assert err.container_id == "abc123"
    assert "removed externally" in str(err)


def test_image_not_found_stores_image() -> None:
    err = ImageNotFound("missing:latest")
    assert err.image == "missing:latest"
    assert "missing:latest" in str(err)


# -- Exported from package --


def test_errors_exported_from_package() -> None:
    assert pocket_dock.PocketDockError is PocketDockError
    assert pocket_dock.SocketError is SocketError
    assert pocket_dock.SocketConnectionError is SocketConnectionError
    assert pocket_dock.SocketCommunicationError is SocketCommunicationError
    assert pocket_dock.PodmanNotRunning is PodmanNotRunning
    assert pocket_dock.ContainerError is ContainerError
    assert pocket_dock.ContainerNotFound is ContainerNotFound
    assert pocket_dock.ContainerNotRunning is ContainerNotRunning
    assert pocket_dock.ContainerGone is ContainerGone
    assert pocket_dock.ImageNotFound is ImageNotFound
