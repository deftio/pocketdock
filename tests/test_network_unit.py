"""Unit tests for network control (issue #21).

Covers ``network`` resolution (explicit argument, profile ``network_default``,
port publishing), ``HostConfig.NetworkMode``, and that the setting survives
``reboot(fresh=True)``, ``resume_container`` and instance metadata.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner
from pocketdock._async_container import (
    AsyncContainer,
    _augment_host_config,
    _resolve_network,
)
from pocketdock._async_container import (
    create_new_container as async_factory,
)
from pocketdock._helpers import parse_binds, parse_devices, parse_network_enabled
from pocketdock.cli.main import cli
from pocketdock.persistence import resume_container
from pocketdock.profiles import PROFILES
from pocketdock.projects import read_instance_metadata, write_instance_metadata

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@contextmanager
def _engine() -> Iterator[AsyncMock]:
    """Patch the engine calls used by create_new_container; yield the create mock."""
    with (
        patch("pocketdock._async_container.sc.detect_socket", return_value="/tmp/s.sock"),
        patch(
            "pocketdock._async_container.sc.create_container",
            new_callable=AsyncMock,
            return_value="deadbeef",
        ) as create,
        patch("pocketdock._async_container.sc.start_container", new_callable=AsyncMock),
    ):
        yield create


def _host_config(create: AsyncMock) -> dict[str, Any] | None:
    hc: dict[str, Any] | None = create.call_args.kwargs["host_config"]
    return hc


# --- _resolve_network ---


@pytest.mark.parametrize(
    ("network", "network_default", "ports", "expected"),
    [
        (None, None, None, True),  # no profile -> on (unchanged behaviour)
        (None, False, None, False),  # profile says off
        (None, True, None, True),  # profile says on
        (True, False, None, True),  # explicit opt-in beats the profile
        (False, True, None, False),  # explicit opt-out beats the profile
        (False, None, None, False),  # explicit opt-out, no profile
        (None, False, {8080: 80}, True),  # ports imply network
        (True, False, {8080: 80}, True),
        (None, False, {}, False),  # empty ports dict does not imply network
        (False, None, {}, False),  # empty ports dict is not a conflict
    ],
)
def test_resolve_network(
    *,
    network: bool | None,
    network_default: bool | None,
    ports: dict[int, int] | None,
    expected: bool,
) -> None:
    assert (
        _resolve_network(network=network, network_default=network_default, ports=ports) is expected
    )


def test_resolve_network_ports_conflict_raises() -> None:
    with pytest.raises(ValueError, match="network=False"):
        _resolve_network(network=False, network_default=None, ports={8080: 80})


# --- _augment_host_config ---


def test_augment_network_off_creates_host_config() -> None:
    assert _augment_host_config(None, network=False) == {"NetworkMode": "none"}


def test_augment_network_off_extends_existing() -> None:
    hc = _augment_host_config({"Memory": 1}, network=False)
    assert hc == {"Memory": 1, "NetworkMode": "none"}


def test_augment_network_on_leaves_mode_unset() -> None:
    assert _augment_host_config(None) is None
    assert _augment_host_config(None, network=True) is None
    assert _augment_host_config({"Memory": 1}, network=True) == {"Memory": 1}


# --- create_new_container ---


async def test_create_no_profile_keeps_network() -> None:
    with _engine() as create:
        c = await async_factory(name="pd-n1")
    assert _host_config(create) is None
    assert c._network is True


@pytest.mark.parametrize("profile", sorted(PROFILES))
async def test_create_applies_profile_network_default(profile: str) -> None:
    with _engine() as create:
        c = await async_factory(name="pd-n2", profile=profile)

    hc = _host_config(create) or {}
    if PROFILES[profile].network_default:
        assert "NetworkMode" not in hc
    else:
        assert hc["NetworkMode"] == "none"
    assert c._network is PROFILES[profile].network_default


async def test_create_agent_profile_is_sandboxed_by_default() -> None:
    with _engine() as create:
        await async_factory(name="pd-agent", profile="agent")
    assert _host_config(create) == {"NetworkMode": "none"}


async def test_create_explicit_network_true_overrides_profile() -> None:
    with _engine() as create:
        c = await async_factory(name="pd-n3", profile="agent", network=True)
    assert _host_config(create) is None
    assert c._network is True


async def test_create_explicit_network_false_overrides_profile() -> None:
    with _engine() as create:
        c = await async_factory(name="pd-n4", profile="dev", network=False)
    assert _host_config(create) == {"NetworkMode": "none"}
    assert c._network is False


async def test_create_network_false_without_profile() -> None:
    with _engine() as create:
        await async_factory(name="pd-n5", network=False, mem_limit="64m")
    assert _host_config(create) == {"Memory": 64 * 1024**2, "NetworkMode": "none"}


async def test_create_profile_network_default_applies_with_explicit_image() -> None:
    with _engine() as create:
        await async_factory(name="pd-n6", image="custom:latest", profile="minimal-python")
    assert create.call_args.args[1] == "custom:latest"
    assert _host_config(create) == {"NetworkMode": "none"}


async def test_create_ports_imply_network_with_no_network_profile() -> None:
    with _engine() as create:
        c = await async_factory(name="pd-n7", profile="minimal-python", ports={8080: 8000})
    hc = _host_config(create)
    assert hc is not None
    assert "NetworkMode" not in hc
    assert hc["PortBindings"] == {"8000/tcp": [{"HostPort": "8080"}]}
    assert c._network is True


async def test_create_ports_with_network_false_raises_before_engine() -> None:
    with (
        patch("pocketdock._async_container.sc.detect_socket") as detect,
        pytest.raises(ValueError, match="network=False"),
    ):
        await async_factory(name="pd-n8", ports={8080: 80}, network=False)
    detect.assert_not_called()


async def test_create_unknown_profile_with_explicit_image_raises() -> None:
    with pytest.raises(ValueError, match="Unknown profile"):
        await async_factory(name="pd-n9", image="custom:latest", profile="nope")


async def test_create_stores_devices_and_volumes() -> None:
    with _engine():
        c = await async_factory(name="pd-n10", devices=["/dev/null"], volumes={"/tmp/h": "/data"})
    assert c._devices == ["/dev/null"]
    assert c._volumes == {"/tmp/h": "/data"}


async def test_create_persist_writes_network_metadata(tmp_path: Path) -> None:
    from pocketdock.projects import init_project

    init_project(tmp_path, project_name="net-proj")
    with _engine(), patch("pocketdock.projects.find_project_root", return_value=tmp_path):
        c = await async_factory(name="pd-n11", persist=True, profile="minimal-python")

    meta = read_instance_metadata(tmp_path / ".pocketdock" / "instances" / c.name)
    assert meta["container"]["network"] is False


# --- reboot(fresh=True) keeps the full config ---


async def test_reboot_fresh_preserves_network_devices_volumes() -> None:
    ac = AsyncContainer(
        "cid",
        "/tmp/s.sock",
        name="pd-rb",
        image="pocketdock/minimal-python",
        mem_limit_bytes=1024,
        devices=["/dev/ttyUSB0"],
        volumes={"/host": "/data"},
        network=False,
    )
    with (
        patch("pocketdock._async_container.sc.stop_container", new_callable=AsyncMock),
        patch("pocketdock._async_container.sc.remove_container", new_callable=AsyncMock),
        patch(
            "pocketdock._async_container.sc.create_container",
            new_callable=AsyncMock,
            return_value="newcid",
        ) as create,
        patch("pocketdock._async_container.sc.start_container", new_callable=AsyncMock),
    ):
        await ac.reboot(fresh=True)

    assert _host_config(create) == {
        "Memory": 1024,
        "Devices": [
            {
                "PathOnHost": "/dev/ttyUSB0",
                "PathInContainer": "/dev/ttyUSB0",
                "CgroupPermissions": "rwm",
            }
        ],
        "Binds": ["/host:/data"],
        "NetworkMode": "none",
    }
    assert ac.container_id == "newcid"


async def test_reboot_fresh_network_on_by_default() -> None:
    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-rb2")
    with (
        patch("pocketdock._async_container.sc.stop_container", new_callable=AsyncMock),
        patch("pocketdock._async_container.sc.remove_container", new_callable=AsyncMock),
        patch(
            "pocketdock._async_container.sc.create_container",
            new_callable=AsyncMock,
            return_value="newcid",
        ) as create,
        patch("pocketdock._async_container.sc.start_container", new_callable=AsyncMock),
    ):
        await ac.reboot(fresh=True)
    assert _host_config(create) is None


# --- inspect parsers ---


@pytest.mark.parametrize(
    ("inspect", "expected"),
    [
        ({"HostConfig": {"NetworkMode": "none"}}, False),
        ({"HostConfig": {"NetworkMode": "bridge"}}, True),
        ({"HostConfig": {"NetworkMode": "default"}}, True),
        ({"HostConfig": {}}, True),
        ({}, True),
    ],
)
def test_parse_network_enabled(inspect: dict[str, object], *, expected: bool) -> None:
    assert parse_network_enabled(inspect) is expected


def test_parse_devices() -> None:
    inspect: dict[str, object] = {
        "HostConfig": {
            "Devices": [
                {"PathOnHost": "/dev/a", "PathInContainer": "/dev/a"},
                {"PathOnHost": ""},
                {"PathInContainer": "/dev/x"},
                "junk",
                {"PathOnHost": "/dev/b"},
            ]
        }
    }
    assert parse_devices(inspect) == ["/dev/a", "/dev/b"]


@pytest.mark.parametrize("raw", [None, "nope", {}])
def test_parse_devices_missing(raw: object) -> None:
    assert parse_devices({"HostConfig": {"Devices": raw}}) == []
    assert parse_devices({}) == []


def test_parse_binds() -> None:
    inspect: dict[str, object] = {
        "HostConfig": {"Binds": ["/h1:/c1", "/h2:/c2:ro", "bad", ":/c3", "/h4:", 42]}
    }
    assert parse_binds(inspect) == {"/h1": "/c1", "/h2": "/c2"}


@pytest.mark.parametrize("raw", [None, "nope", {}])
def test_parse_binds_missing(raw: object) -> None:
    assert parse_binds({"HostConfig": {"Binds": raw}}) == {}
    assert parse_binds({}) == {}


# --- resume_container restores the config ---


async def _resume(inspect_result: dict[str, Any]) -> AsyncContainer:
    with (
        patch("pocketdock.persistence.sc.detect_socket", return_value="/tmp/s.sock"),
        patch(
            "pocketdock.persistence.sc.list_containers",
            new_callable=AsyncMock,
            return_value=[{"Id": "abc", "State": "running"}],
        ),
        patch(
            "pocketdock.persistence.sc.inspect_container",
            new_callable=AsyncMock,
            return_value=inspect_result,
        ),
    ):
        return await resume_container("pd-res")


async def test_resume_restores_network_off_devices_volumes() -> None:
    c = await _resume(
        {
            "State": {"Running": True},
            "Config": {"Image": "img", "Labels": {}},
            "HostConfig": {
                "NetworkMode": "none",
                "Devices": [{"PathOnHost": "/dev/ttyUSB0"}],
                "Binds": ["/h:/c"],
            },
        }
    )
    assert c._network is False
    assert c._devices == ["/dev/ttyUSB0"]
    assert c._volumes == {"/h": "/c"}


async def test_resume_network_on_and_no_devices_volumes() -> None:
    c = await _resume(
        {
            "State": {"Running": True},
            "Config": {"Image": "img", "Labels": {}},
            "HostConfig": {"NetworkMode": "bridge", "Devices": [], "Binds": None},
        }
    )
    assert c._network is True
    assert c._devices is None
    assert c._volumes is None


# --- instance metadata ---


def test_write_instance_metadata_network_default_true(tmp_path: Path) -> None:
    write_instance_metadata(tmp_path, name="x")
    assert read_instance_metadata(tmp_path)["container"]["network"] is True


def test_write_instance_metadata_network_false(tmp_path: Path) -> None:
    write_instance_metadata(tmp_path, name="x", network=False)
    assert read_instance_metadata(tmp_path)["container"]["network"] is False


# --- sync facade ---


@pytest.mark.parametrize("network", [None, True, False])
def test_sync_create_passes_network(network: bool | None) -> None:  # noqa: FBT001
    import pocketdock._sync_container as sync_mod

    mock_lt = MagicMock()
    with (
        patch.object(sync_mod._LoopThread, "get", return_value=mock_lt),
        patch.object(sync_mod, "_async_create", new=MagicMock()) as async_create,
    ):
        sync_mod.create_new_container(profile="agent", network=network)

    assert async_create.call_args.kwargs["network"] is network
    assert async_create.call_args.kwargs["profile"] == "agent"


# --- CLI ---


def _cli_container() -> MagicMock:
    container = MagicMock()
    container.name = "test"
    container.container_id = "abc123def456"
    return container


@pytest.mark.parametrize(("flag", "expected"), [("--network", True), ("--no-network", False)])
@patch("pocketdock.create_new_container")
def test_cli_create_network_flags(mock_create: MagicMock, flag: str, *, expected: bool) -> None:
    mock_create.return_value = _cli_container()
    result = CliRunner().invoke(cli, ["create", "--profile", "agent", flag])
    assert result.exit_code == 0, result.output
    assert mock_create.call_args.kwargs["network"] is expected


@patch("pocketdock.create_new_container")
def test_cli_create_without_network_flag_omits_kwarg(mock_create: MagicMock) -> None:
    mock_create.return_value = _cli_container()
    result = CliRunner().invoke(cli, ["create"])
    assert result.exit_code == 0
    assert "network" not in mock_create.call_args.kwargs


@patch("pocketdock.create_new_container")
def test_cli_create_no_network_with_port_is_usage_error(mock_create: MagicMock) -> None:
    result = CliRunner().invoke(cli, ["create", "--no-network", "-p", "8080:80"])
    assert result.exit_code == 2
    assert "--no-network cannot be combined with --port" in result.output
    mock_create.assert_not_called()


@patch("pocketdock.create_new_container", side_effect=ValueError("Unknown profile 'zzz'"))
def test_cli_create_value_error_is_clean(mock_create: MagicMock) -> None:
    result = CliRunner().invoke(cli, ["create", "--profile", "zzz"])
    assert result.exit_code == 1
    assert "Unknown profile 'zzz'" in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)
    mock_create.assert_called_once()


def test_cli_create_help_lists_network_flag() -> None:
    result = CliRunner().invoke(cli, ["create", "--help"])
    assert "--network / --no-network" in result.output
