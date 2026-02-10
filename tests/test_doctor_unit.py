"""Unit tests for the doctor() command in projects.py.

All tests use tmp_path for filesystem isolation and mock the engine query.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from pocket_dock.errors import ProjectNotInitialized
from pocket_dock.projects import doctor, init_project
from pocket_dock.types import ContainerListItem

if TYPE_CHECKING:
    from pathlib import Path


def _make_item(name: str, project: str = "myproj") -> ContainerListItem:
    return ContainerListItem(
        id="abc123",
        name=name,
        status="running",
        image="pocket-dock/minimal",
        created_at="2026-01-01T00:00:00Z",
        persist=True,
        project=project,
    )


# --- doctor: raises on missing project ---


@pytest.mark.asyncio
async def test_doctor_raises_when_no_project(tmp_path: Path) -> None:
    with pytest.raises(ProjectNotInitialized):
        await doctor(project_root=tmp_path)


# --- doctor: empty project (no instances, no containers) ---


@pytest.mark.asyncio
async def test_doctor_empty_project(tmp_path: Path) -> None:
    init_project(tmp_path, project_name="myproj")

    with patch(
        "pocket_dock.persistence.list_containers",
        new_callable=AsyncMock,
        return_value=[],
    ):
        report = await doctor(project_root=tmp_path, socket_path="/fake.sock")

    assert report.orphaned_containers == ()
    assert report.stale_instance_dirs == ()
    assert report.healthy == 0


# --- doctor: all healthy ---


@pytest.mark.asyncio
async def test_doctor_all_healthy(tmp_path: Path) -> None:
    init_project(tmp_path, project_name="myproj")
    inst_dir = tmp_path / ".pocket-dock" / "instances" / "inst-a"
    inst_dir.mkdir(parents=True)

    with patch(
        "pocket_dock.persistence.list_containers",
        new_callable=AsyncMock,
        return_value=[_make_item("inst-a")],
    ):
        report = await doctor(project_root=tmp_path, socket_path="/fake.sock")

    assert report.orphaned_containers == ()
    assert report.stale_instance_dirs == ()
    assert report.healthy == 1


# --- doctor: orphaned containers (in engine, not on disk) ---


@pytest.mark.asyncio
async def test_doctor_orphaned_containers(tmp_path: Path) -> None:
    init_project(tmp_path, project_name="myproj")

    with patch(
        "pocket_dock.persistence.list_containers",
        new_callable=AsyncMock,
        return_value=[_make_item("orphan-a"), _make_item("orphan-b")],
    ):
        report = await doctor(project_root=tmp_path, socket_path="/fake.sock")

    assert report.orphaned_containers == ("orphan-a", "orphan-b")
    assert report.stale_instance_dirs == ()
    assert report.healthy == 0


# --- doctor: stale instance dirs (on disk, not in engine) ---


@pytest.mark.asyncio
async def test_doctor_stale_instance_dirs(tmp_path: Path) -> None:
    init_project(tmp_path, project_name="myproj")
    (tmp_path / ".pocket-dock" / "instances" / "stale-x").mkdir(parents=True)
    (tmp_path / ".pocket-dock" / "instances" / "stale-y").mkdir(parents=True)

    with patch(
        "pocket_dock.persistence.list_containers",
        new_callable=AsyncMock,
        return_value=[],
    ):
        report = await doctor(project_root=tmp_path, socket_path="/fake.sock")

    assert report.orphaned_containers == ()
    assert report.stale_instance_dirs == ("stale-x", "stale-y")
    assert report.healthy == 0


# --- doctor: mixed state ---


@pytest.mark.asyncio
async def test_doctor_mixed_state(tmp_path: Path) -> None:
    init_project(tmp_path, project_name="myproj")
    (tmp_path / ".pocket-dock" / "instances" / "healthy-a").mkdir(parents=True)
    (tmp_path / ".pocket-dock" / "instances" / "stale-z").mkdir(parents=True)

    with patch(
        "pocket_dock.persistence.list_containers",
        new_callable=AsyncMock,
        return_value=[_make_item("healthy-a"), _make_item("orphan-q")],
    ):
        report = await doctor(project_root=tmp_path, socket_path="/fake.sock")

    assert report.orphaned_containers == ("orphan-q",)
    assert report.stale_instance_dirs == ("stale-z",)
    assert report.healthy == 1


# --- doctor: auto-detects project root ---


@pytest.mark.asyncio
async def test_doctor_auto_detects_project_root(tmp_path: Path) -> None:
    init_project(tmp_path, project_name="auto")

    with (
        patch("pocket_dock.projects.find_project_root", return_value=tmp_path),
        patch(
            "pocket_dock.persistence.list_containers",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        report = await doctor(socket_path="/fake.sock")

    assert report.healthy == 0


# --- doctor: auto-detect returns None raises ---


@pytest.mark.asyncio
async def test_doctor_auto_detect_none_raises() -> None:
    with (
        patch("pocket_dock.projects.find_project_root", return_value=None),
        pytest.raises(ProjectNotInitialized),
    ):
        await doctor(socket_path="/fake.sock")


# --- doctor: multiple healthy ---


@pytest.mark.asyncio
async def test_doctor_multiple_healthy(tmp_path: Path) -> None:
    init_project(tmp_path, project_name="myproj")
    for name in ("a", "b", "c"):
        (tmp_path / ".pocket-dock" / "instances" / name).mkdir(parents=True)

    with patch(
        "pocket_dock.persistence.list_containers",
        new_callable=AsyncMock,
        return_value=[_make_item("a"), _make_item("b"), _make_item("c")],
    ):
        report = await doctor(project_root=tmp_path, socket_path="/fake.sock")

    assert report.orphaned_containers == ()
    assert report.stale_instance_dirs == ()
    assert report.healthy == 3


# --- doctor: uses project name from yaml ---


@pytest.mark.asyncio
async def test_doctor_uses_project_name_from_yaml(tmp_path: Path) -> None:
    init_project(tmp_path, project_name="custom-name")
    (tmp_path / ".pocket-dock" / "instances" / "x").mkdir(parents=True)

    mock_lc = AsyncMock(return_value=[_make_item("x", project="custom-name")])
    with patch("pocket_dock.persistence.list_containers", mock_lc):
        await doctor(project_root=tmp_path, socket_path="/fake.sock")

    # Verify list_containers was called with the project name from yaml
    mock_lc.assert_called_once_with(socket_path="/fake.sock", project="custom-name")
