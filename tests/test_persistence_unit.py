"""Unit tests for persistence management functions.

These tests do NOT require a running container engine.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pocket_dock.errors import ContainerNotFound, PodmanNotRunning
from pocket_dock.persistence import (
    _parse_container_list_item,
    _resolve_socket,
    destroy_container,
    list_containers,
    prune,
    resume_container,
)
from pocket_dock.types import ContainerListItem

# --- _resolve_socket ---


def test_resolve_socket_returns_provided() -> None:
    assert _resolve_socket("/tmp/custom.sock") == "/tmp/custom.sock"


def test_resolve_socket_detects_when_none() -> None:
    with patch("pocket_dock.persistence.sc.detect_socket", return_value="/tmp/auto.sock"):
        assert _resolve_socket(None) == "/tmp/auto.sock"


def test_resolve_socket_raises_when_no_engine() -> None:
    with (
        patch("pocket_dock.persistence.sc.detect_socket", return_value=None),
        pytest.raises(PodmanNotRunning),
    ):
        _resolve_socket(None)


# --- _parse_container_list_item ---


def test_parse_full_data() -> None:
    data = {
        "Id": "abc123def45678",
        "Names": ["pd-test"],
        "State": "running",
        "Image": "pocket-dock/minimal",
        "Labels": {
            "pocket-dock.instance": "pd-test",
            "pocket-dock.persist": "true",
            "pocket-dock.created-at": "2026-02-09T00:00:00+00:00",
        },
    }
    item = _parse_container_list_item(data)
    assert item.id == "abc123def456"
    assert item.name == "pd-test"
    assert item.status == "running"
    assert item.image == "pocket-dock/minimal"
    assert item.persist is True
    assert item.created_at == "2026-02-09T00:00:00+00:00"


def test_parse_no_labels_uses_names() -> None:
    data = {
        "Id": "abc123",
        "Names": ["/docker-name"],
        "State": "exited",
        "Image": "img",
        "Labels": {},
    }
    item = _parse_container_list_item(data)
    assert item.name == "docker-name"
    assert item.persist is False
    assert item.created_at == ""


def test_parse_empty_data() -> None:
    item = _parse_container_list_item({})
    assert item.id == ""
    assert item.name == ""
    assert item.status == "unknown"
    assert item.image == ""
    assert item.persist is False


def test_parse_none_labels() -> None:
    data = {"Id": "abc", "Labels": None, "Names": None, "State": "running", "Image": "img"}
    item = _parse_container_list_item(data)
    assert item.name == ""
    assert item.persist is False


def test_parse_persist_false_label() -> None:
    data = {
        "Id": "abc123def456",
        "Names": ["n"],
        "State": "running",
        "Image": "img",
        "Labels": {"pocket-dock.persist": "false"},
    }
    item = _parse_container_list_item(data)
    assert item.persist is False


def test_container_list_item_is_frozen() -> None:
    item = ContainerListItem(
        id="x", name="n", status="running", image="img", created_at="", persist=False
    )
    with pytest.raises(AttributeError):
        item.name = "changed"  # type: ignore[misc]


# --- resume_container ---


async def test_resume_no_socket_raises() -> None:
    with (
        patch("pocket_dock.persistence.sc.detect_socket", return_value=None),
        pytest.raises(PodmanNotRunning),
    ):
        await resume_container("test")


async def test_resume_not_found() -> None:
    with (
        patch("pocket_dock.persistence.sc.detect_socket", return_value="/tmp/s.sock"),
        patch(
            "pocket_dock.persistence.sc.list_containers",
            new_callable=AsyncMock,
            return_value=[],
        ),
        pytest.raises(ContainerNotFound),
    ):
        await resume_container("missing")


async def test_resume_stopped_container_starts_it() -> None:
    list_result = [{"Id": "abc123", "State": "exited"}]
    inspect_result = {
        "Config": {
            "Image": "pocket-dock/minimal",
            "Labels": {"pocket-dock.persist": "true"},
        },
        "HostConfig": {"Memory": 0, "NanoCpus": 0},
    }
    with (
        patch("pocket_dock.persistence.sc.detect_socket", return_value="/tmp/s.sock"),
        patch(
            "pocket_dock.persistence.sc.list_containers",
            new_callable=AsyncMock,
            return_value=list_result,
        ),
        patch("pocket_dock.persistence.sc.start_container", new_callable=AsyncMock) as start,
        patch(
            "pocket_dock.persistence.sc.inspect_container",
            new_callable=AsyncMock,
            return_value=inspect_result,
        ),
    ):
        c = await resume_container("pd-test")

    start.assert_called_once_with("/tmp/s.sock", "abc123")
    assert c.container_id == "abc123"
    assert c.persist is True
    assert c.name == "pd-test"


async def test_resume_running_container_skips_start() -> None:
    list_result = [{"Id": "abc123", "State": "running"}]
    inspect_result = {
        "Config": {"Image": "img", "Labels": {}},
        "HostConfig": {"Memory": 268435456, "NanoCpus": 500000000},
    }
    with (
        patch("pocket_dock.persistence.sc.detect_socket", return_value="/tmp/s.sock"),
        patch(
            "pocket_dock.persistence.sc.list_containers",
            new_callable=AsyncMock,
            return_value=list_result,
        ),
        patch("pocket_dock.persistence.sc.start_container", new_callable=AsyncMock) as start,
        patch(
            "pocket_dock.persistence.sc.inspect_container",
            new_callable=AsyncMock,
            return_value=inspect_result,
        ),
    ):
        c = await resume_container("pd-test")

    start.assert_not_called()
    assert c.container_id == "abc123"


async def test_resume_with_explicit_socket() -> None:
    list_result = [{"Id": "abc123", "State": "exited"}]
    inspect_result = {
        "Config": {"Image": "img", "Labels": {}},
        "HostConfig": {"Memory": 0, "NanoCpus": 0},
    }
    with (
        patch(
            "pocket_dock.persistence.sc.list_containers",
            new_callable=AsyncMock,
            return_value=list_result,
        ) as list_mock,
        patch("pocket_dock.persistence.sc.start_container", new_callable=AsyncMock),
        patch(
            "pocket_dock.persistence.sc.inspect_container",
            new_callable=AsyncMock,
            return_value=inspect_result,
        ),
    ):
        await resume_container("pd-test", socket_path="/custom.sock")

    list_mock.assert_called_once_with("/custom.sock", label_filter="pocket-dock.instance=pd-test")


# --- list_containers ---


async def test_list_no_socket_raises() -> None:
    with (
        patch("pocket_dock.persistence.sc.detect_socket", return_value=None),
        pytest.raises(PodmanNotRunning),
    ):
        await list_containers()


async def test_list_returns_parsed_items() -> None:
    raw = [
        {
            "Id": "abc123def456",
            "State": "running",
            "Image": "img",
            "Names": ["n"],
            "Labels": {"pocket-dock.instance": "pd-a"},
        },
        {
            "Id": "def456abc123",
            "State": "exited",
            "Image": "img2",
            "Names": ["m"],
            "Labels": {"pocket-dock.instance": "pd-b", "pocket-dock.persist": "true"},
        },
    ]
    with (
        patch("pocket_dock.persistence.sc.detect_socket", return_value="/tmp/s.sock"),
        patch(
            "pocket_dock.persistence.sc.list_containers",
            new_callable=AsyncMock,
            return_value=raw,
        ),
    ):
        result = await list_containers()

    assert len(result) == 2
    assert all(isinstance(r, ContainerListItem) for r in result)
    assert result[0].name == "pd-a"
    assert result[1].persist is True


async def test_list_empty() -> None:
    with (
        patch("pocket_dock.persistence.sc.detect_socket", return_value="/tmp/s.sock"),
        patch(
            "pocket_dock.persistence.sc.list_containers",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        result = await list_containers()

    assert result == []


# --- destroy_container ---


async def test_destroy_no_socket_raises() -> None:
    with (
        patch("pocket_dock.persistence.sc.detect_socket", return_value=None),
        pytest.raises(PodmanNotRunning),
    ):
        await destroy_container("test")


async def test_destroy_not_found_raises() -> None:
    with (
        patch("pocket_dock.persistence.sc.detect_socket", return_value="/tmp/s.sock"),
        patch(
            "pocket_dock.persistence.sc.list_containers",
            new_callable=AsyncMock,
            return_value=[],
        ),
        pytest.raises(ContainerNotFound),
    ):
        await destroy_container("missing")


async def test_destroy_removes_with_force() -> None:
    with (
        patch("pocket_dock.persistence.sc.detect_socket", return_value="/tmp/s.sock"),
        patch(
            "pocket_dock.persistence.sc.list_containers",
            new_callable=AsyncMock,
            return_value=[{"Id": "abc123"}],
        ),
        patch("pocket_dock.persistence.sc.remove_container", new_callable=AsyncMock) as remove,
    ):
        await destroy_container("test")

    remove.assert_called_once_with("/tmp/s.sock", "abc123", force=True)


# --- prune ---


async def test_prune_no_socket_raises() -> None:
    with (
        patch("pocket_dock.persistence.sc.detect_socket", return_value=None),
        pytest.raises(PodmanNotRunning),
    ):
        await prune()


async def test_prune_removes_stopped_only() -> None:
    raw = [
        {"Id": "running1", "State": "running"},
        {"Id": "exited1", "State": "exited"},
        {"Id": "exited2", "State": "exited"},
    ]
    with (
        patch("pocket_dock.persistence.sc.detect_socket", return_value="/tmp/s.sock"),
        patch(
            "pocket_dock.persistence.sc.list_containers",
            new_callable=AsyncMock,
            return_value=raw,
        ),
        patch("pocket_dock.persistence.sc.remove_container", new_callable=AsyncMock) as remove,
    ):
        count = await prune()

    assert count == 2
    assert remove.call_count == 2
    removed_ids = [call.args[1] for call in remove.call_args_list]
    assert "exited1" in removed_ids
    assert "exited2" in removed_ids
    assert "running1" not in removed_ids


async def test_prune_no_stopped_returns_zero() -> None:
    raw = [{"Id": "running1", "State": "running"}]
    with (
        patch("pocket_dock.persistence.sc.detect_socket", return_value="/tmp/s.sock"),
        patch(
            "pocket_dock.persistence.sc.list_containers",
            new_callable=AsyncMock,
            return_value=raw,
        ),
        patch("pocket_dock.persistence.sc.remove_container", new_callable=AsyncMock) as remove,
    ):
        count = await prune()

    assert count == 0
    remove.assert_not_called()


async def test_prune_empty_list_returns_zero() -> None:
    with (
        patch("pocket_dock.persistence.sc.detect_socket", return_value="/tmp/s.sock"),
        patch(
            "pocket_dock.persistence.sc.list_containers",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        count = await prune()

    assert count == 0
