# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Persistence management — resume, list, destroy, and prune containers."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from pocketdock import _socket_client as sc
from pocketdock._async_container import AsyncContainer
from pocketdock._helpers import parse_port_bindings
from pocketdock.errors import ContainerNotFound, PodmanNotRunning
from pocketdock.types import ContainerListItem


async def resume_container(
    name: str,
    *,
    socket_path: str | None = None,
    timeout: int = 30,
) -> AsyncContainer:
    """Resume a stopped persistent container by name.

    Args:
        name: The container name (``pocketdock.instance`` label value).
        socket_path: Path to the engine socket. Auto-detected if ``None``.
        timeout: Default exec timeout for the resumed container.

    Returns:
        A running :class:`AsyncContainer`.

    Raises:
        ContainerNotFound: If no container with this name exists.
        PodmanNotRunning: If no container engine socket is found.

    """
    socket_path = _resolve_socket(socket_path)

    containers = await sc.list_containers(
        socket_path,
        label_filter=f"pocketdock.instance={name}",
    )
    if not containers:
        raise ContainerNotFound(name)

    container_data = containers[0]
    container_id: str = container_data["Id"]

    state = container_data.get("State", "").lower()
    if state != "running":
        await sc.start_container(socket_path, container_id)

    inspect_data = await sc.inspect_container(socket_path, container_id)
    config = inspect_data.get("Config", {})
    labels = config.get("Labels", {})
    image = config.get("Image", "")
    host_config = inspect_data.get("HostConfig", {})

    mem_limit_bytes = int(host_config.get("Memory", 0))
    nano_cpus = int(host_config.get("NanoCpus", 0))
    persist = labels.get("pocketdock.persist", "false").lower() == "true"
    project = labels.get("pocketdock.project", "")
    data_path = labels.get("pocketdock.data-path", "")
    ports = parse_port_bindings(inspect_data)

    return AsyncContainer(
        container_id,
        socket_path,
        name=name,
        image=image,
        timeout=timeout,
        mem_limit_bytes=mem_limit_bytes,
        nano_cpus=nano_cpus,
        persist=persist,
        project=project,
        data_path=data_path,
        ports=ports or None,
    )


async def list_containers(
    *,
    socket_path: str | None = None,
    project: str | None = None,
) -> list[ContainerListItem]:
    """List all pocketdock managed containers.

    Args:
        socket_path: Path to the engine socket. Auto-detected if ``None``.
        project: If given, only list containers belonging to this project.

    Returns:
        List of :class:`ContainerListItem` objects.

    Raises:
        PodmanNotRunning: If no container engine socket is found.

    """
    socket_path = _resolve_socket(socket_path)
    label_filter = "pocketdock.managed=true"
    if project is not None:
        label_filter = f"pocketdock.project={project}"
    raw = await sc.list_containers(
        socket_path,
        label_filter=label_filter,
    )
    return [_parse_container_list_item(c) for c in raw]


async def destroy_container(
    name: str,
    *,
    socket_path: str | None = None,
) -> None:
    """Remove a container completely, whether running or stopped.

    Args:
        name: The container name.
        socket_path: Path to the engine socket. Auto-detected if ``None``.

    Raises:
        ContainerNotFound: If no container with this name exists.
        PodmanNotRunning: If no container engine socket is found.

    """
    socket_path = _resolve_socket(socket_path)

    containers = await sc.list_containers(
        socket_path,
        label_filter=f"pocketdock.instance={name}",
    )
    if not containers:
        raise ContainerNotFound(name)

    container_data = containers[0]
    container_id: str = container_data["Id"]

    # Check for data-path label to clean up instance directory
    inspect_data = await sc.inspect_container(socket_path, container_id)
    labels = inspect_data.get("Config", {}).get("Labels", {}) or {}
    data_path = labels.get("pocketdock.data-path", "")

    await sc.remove_container(socket_path, container_id, force=True)

    if data_path:
        dp = Path(data_path)
        if dp.is_dir():  # noqa: ASYNC240
            shutil.rmtree(dp)


async def prune(
    *,
    socket_path: str | None = None,
    project: str | None = None,
) -> int:
    """Remove all stopped pocketdock containers.

    Args:
        socket_path: Path to the engine socket. Auto-detected if ``None``.
        project: If given, only prune containers belonging to this project.

    Returns:
        Number of containers removed.

    Raises:
        PodmanNotRunning: If no container engine socket is found.

    """
    socket_path = _resolve_socket(socket_path)

    label_filter = "pocketdock.managed=true"
    if project is not None:
        label_filter = f"pocketdock.project={project}"
    raw = await sc.list_containers(
        socket_path,
        label_filter=label_filter,
    )
    count = 0
    for container in raw:
        state = container.get("State", "").lower()
        if state != "running":
            await sc.remove_container(socket_path, container["Id"], force=True)
            count += 1
    return count


async def stop_container(
    name: str,
    *,
    socket_path: str | None = None,
) -> None:
    """Stop a running container by name (without removing).

    Args:
        name: The container name (``pocketdock.instance`` label value).
        socket_path: Path to the engine socket. Auto-detected if ``None``.

    Raises:
        ContainerNotFound: If no container with this name exists.
        PodmanNotRunning: If no container engine socket is found.

    """
    socket_path = _resolve_socket(socket_path)

    containers = await sc.list_containers(
        socket_path,
        label_filter=f"pocketdock.instance={name}",
    )
    if not containers:
        raise ContainerNotFound(name)

    container_id: str = containers[0]["Id"]
    await sc.stop_container(socket_path, container_id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_socket(socket_path: str | None) -> str:
    """Return a validated socket path, auto-detecting if necessary."""
    if socket_path is not None:
        return socket_path
    detected = sc.detect_socket()
    if detected is None:
        raise PodmanNotRunning
    return detected


def _parse_container_list_item(data: dict[str, Any]) -> ContainerListItem:
    """Parse a raw container JSON object into a ContainerListItem."""
    labels = data.get("Labels") or {}
    names = data.get("Names") or []

    name = labels.get("pocketdock.instance", "")
    if not name and names:
        # Docker prefixes names with "/"; Podman does not
        name = names[0].lstrip("/")

    return ContainerListItem(
        id=data.get("Id", "")[:12],
        name=name,
        status=data.get("State", "unknown"),
        image=data.get("Image", ""),
        created_at=labels.get("pocketdock.created-at", ""),
        persist=labels.get("pocketdock.persist", "false").lower() == "true",
        project=labels.get("pocketdock.project", ""),
    )
