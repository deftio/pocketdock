"""Shared fixtures for pocketdock tests."""

from __future__ import annotations

import os
import pathlib

import pytest


def _path_exists(path: pathlib.Path) -> bool:
    """Check if *path* exists, returning ``False`` on ``PermissionError``."""
    try:
        return path.exists()
    except PermissionError:
        return False


def _find_socket() -> str | None:
    """Detect an available container engine socket."""
    explicit = os.environ.get("POCKETDOCK_SOCKET")
    if explicit and _path_exists(pathlib.Path(explicit)):
        return explicit

    xdg = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    candidates = [
        pathlib.Path(xdg) / "podman" / "podman.sock",
        pathlib.Path("/run/podman/podman.sock"),
        pathlib.Path("/var/run/docker.sock"),
    ]
    for candidate in candidates:
        if _path_exists(candidate):
            return str(candidate)
    return None


SOCKET_PATH = _find_socket()
HAS_ENGINE = SOCKET_PATH is not None

requires_engine = pytest.mark.skipif(
    not HAS_ENGINE,
    reason="No container engine socket found (Podman or Docker)",
)


@pytest.fixture
def socket_path() -> str:
    """Return the detected socket path, or skip the test."""
    if SOCKET_PATH is None:
        pytest.skip("No container engine socket found")
    return SOCKET_PATH
