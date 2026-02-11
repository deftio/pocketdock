"""Integration tests for persistence functionality.

Requires a running container engine (Podman or Docker).
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from pocketdock import _socket_client as sc

if TYPE_CHECKING:
    import pytest
from pocketdock.async_ import create_new_container
from pocketdock.persistence import (
    destroy_container,
    list_containers,
    prune,
    resume_container,
)
from pocketdock.projects import init_project

from .conftest import requires_engine

# --- Helper ---


async def _force_cleanup(name: str) -> None:
    """Best-effort cleanup of a container by name."""
    socket_path = sc.detect_socket()
    if socket_path is None:
        return
    with contextlib.suppress(Exception):
        containers = await sc.list_containers(
            socket_path, label_filter=f"pocketdock.instance={name}"
        )
        for ct in containers:
            with contextlib.suppress(Exception):
                await sc.remove_container(socket_path, ct["Id"], force=True)


# --- persist=True round-trip ---


@requires_engine
async def test_persist_shutdown_resume_preserves_state() -> None:
    c = await create_new_container(persist=True)
    name = c.name
    try:
        result = await c.run("touch /tmp/persistence-marker && echo ok")
        assert result.ok
        await c.shutdown()

        c2 = await resume_container(name)
        try:
            result2 = await c2.run("ls /tmp/persistence-marker")
            assert result2.ok
        finally:
            await c2.shutdown()
            await destroy_container(name)
    except BaseException:
        await _force_cleanup(name)
        raise


# --- snapshot ---


@requires_engine
async def test_snapshot_creates_usable_image() -> None:
    c = await create_new_container()
    image_name = "pocketdock-test/snapshot-test:v1"
    try:
        result = await c.run("touch /tmp/snapshot-marker && echo ok")
        assert result.ok
        image_id = await c.snapshot(image_name)
        assert image_id
    finally:
        await c.shutdown()

    c2 = await create_new_container(image=image_name)
    try:
        result2 = await c2.run("ls /tmp/snapshot-marker")
        assert result2.ok
    finally:
        await c2.shutdown()


# --- list_containers ---


@requires_engine
async def test_list_containers_includes_created() -> None:
    c = await create_new_container()
    try:
        items = await list_containers()
        names = [item.name for item in items]
        assert c.name in names
    finally:
        await c.shutdown()


@requires_engine
async def test_list_containers_shows_persist_flag() -> None:
    c = await create_new_container(persist=True)
    name = c.name
    try:
        items = await list_containers()
        match = [item for item in items if item.name == name]
        assert len(match) == 1
        assert match[0].persist is True
    finally:
        await c.shutdown()
        await destroy_container(name)


# --- destroy_container ---


@requires_engine
async def test_destroy_removes_persistent_container() -> None:
    c = await create_new_container(persist=True)
    name = c.name
    await c.shutdown()

    await destroy_container(name)

    items = await list_containers()
    names = [item.name for item in items]
    assert name not in names


# --- prune ---


@requires_engine
async def test_prune_removes_stopped_containers() -> None:
    c = await create_new_container(persist=True)
    name = c.name
    await c.shutdown()

    count = await prune()
    assert count >= 1

    items = await list_containers()
    names = [item.name for item in items]
    assert name not in names


# --- volume mounts ---


@requires_engine
async def test_volume_mount(tmp_path: pytest.TempPathFactory) -> None:  # type: ignore[type-arg]
    import pathlib

    host_dir = pathlib.Path(str(tmp_path)) / "vol-test"
    host_dir.mkdir(parents=True, exist_ok=True)
    host_dir.chmod(0o777)  # rootless Podman: container user needs write access

    c = await create_new_container(volumes={str(host_dir): "/mnt/shared"})
    try:
        result = await c.run("echo 'from-container' > /mnt/shared/test.txt && echo ok")
        assert result.ok

        result2 = await c.run("cat /mnt/shared/test.txt")
        assert "from-container" in result2.stdout

        assert (host_dir / "test.txt").exists()
        assert "from-container" in (host_dir / "test.txt").read_text()
    finally:
        await c.shutdown()


# --- project integration ---


@requires_engine
async def test_persist_with_project_sets_labels(
    tmp_path: pytest.TempPathFactory,  # type: ignore[type-arg]
) -> None:
    import pathlib

    project_dir = pathlib.Path(str(tmp_path)) / "proj"
    project_dir.mkdir()
    init_project(project_dir, project_name="integ-test")

    c = await create_new_container(persist=True, project="integ-test")
    name = c.name
    try:
        # Verify project label is set
        socket_path = c.socket_path
        containers = await sc.list_containers(
            socket_path, label_filter=f"pocketdock.instance={name}"
        )
        assert len(containers) == 1
        labels = containers[0].get("Labels", {})
        assert labels.get("pocketdock.project") == "integ-test"
    finally:
        await c.shutdown()
        await destroy_container(name)


@requires_engine
async def test_list_containers_project_filter() -> None:
    c1 = await create_new_container(persist=True, project="proj-a")
    c2 = await create_new_container(persist=True, project="proj-b")
    name1, name2 = c1.name, c2.name
    try:
        items_a = await list_containers(project="proj-a")
        items_b = await list_containers(project="proj-b")

        names_a = [item.name for item in items_a]
        names_b = [item.name for item in items_b]

        assert name1 in names_a
        assert name2 not in names_a
        assert name2 in names_b
        assert name1 not in names_b
    finally:
        await c1.shutdown()
        await c2.shutdown()
        await destroy_container(name1)
        await destroy_container(name2)


@requires_engine
async def test_prune_with_project_filter() -> None:
    c1 = await create_new_container(persist=True, project="prune-a")
    c2 = await create_new_container(persist=True, project="prune-b")
    name1, name2 = c1.name, c2.name
    await c1.shutdown()
    await c2.shutdown()

    # Prune only project "prune-a"
    count = await prune(project="prune-a")
    assert count >= 1

    # c1 should be gone, c2 should remain
    items = await list_containers()
    remaining = [item.name for item in items]
    assert name1 not in remaining
    assert name2 in remaining

    # Clean up c2
    await destroy_container(name2)
