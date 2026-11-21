"""Integration tests for network control (issue #21).

Requires a running container engine (Podman or Docker) and the
``pocketdock/minimal-python`` image.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pocketdock import _socket_client as sc
from pocketdock.async_ import AsyncContainer, create_new_container

from .conftest import requires_engine

if TYPE_CHECKING:
    from pathlib import Path

# Opens a TCP connection to a public IP.  With NetworkMode=none there is no
# route, so it fails immediately (ENETUNREACH) without needing internet access.
_CONNECT = (
    "import socket\n"
    "s = socket.socket()\n"
    "s.settimeout(3)\n"
    "try:\n"
    "    s.connect(('1.1.1.1', 53))\n"
    "    print('connected')\n"
    "except OSError as e:\n"
    "    print('blocked', e.errno)\n"
)


async def _routes(c: AsyncContainer) -> list[str]:
    """Return the container's IPv4 routes (``/proc/net/route`` minus the header).

    ``NetworkMode=none`` leaves only loopback, which has no IPv4 route entry.
    (``/sys/class/net`` is not used: some engine kernels list tunnel
    pseudo-devices there even without a network.)
    """
    result = await c.run("cat /proc/net/route")
    assert result.ok, result.stderr
    return [line for line in result.stdout.splitlines()[1:] if line.strip()]


async def _network_mode(c: AsyncContainer) -> str:
    data = await sc.inspect_container(c.socket_path, c.container_id)
    return str(data["HostConfig"].get("NetworkMode", ""))


@requires_engine
async def test_no_network_profile_has_loopback_only() -> None:
    async with await create_new_container(profile="minimal-python") as c:
        assert await _network_mode(c) == "none"
        assert await _routes(c) == []
        result = await c.run(_CONNECT, lang="python")
        assert result.stdout.startswith("blocked"), result.stdout
        info = await c.info()
        assert info.network is False
        assert info.ip_address == ""


@requires_engine
async def test_network_true_overrides_profile() -> None:
    async with await create_new_container(profile="minimal-python", network=True) as c:
        assert await _network_mode(c) != "none"
        assert await _routes(c) != []
        info = await c.info()
        assert info.network is True


@requires_engine
async def test_no_profile_keeps_network() -> None:
    async with await create_new_container() as c:
        assert await _network_mode(c) != "none"
        assert await _routes(c) != []


@requires_engine
async def test_network_false_without_profile() -> None:
    async with await create_new_container(network=False) as c:
        assert await _network_mode(c) == "none"
        assert await _routes(c) == []


@requires_engine
async def test_ports_imply_network_on_no_network_profile() -> None:
    async with await create_new_container(profile="minimal-python", ports={18731: 8000}) as c:
        assert await _network_mode(c) != "none"
        data = await sc.inspect_container(c.socket_path, c.container_id)
        bindings = data["HostConfig"]["PortBindings"]
        assert bindings["8000/tcp"][0]["HostPort"] == "18731"


@requires_engine
async def test_ports_with_network_false_raises() -> None:
    with pytest.raises(ValueError, match="network=False"):
        await create_new_container(ports={18732: 8000}, network=False)


@requires_engine
async def test_reboot_fresh_keeps_network_off() -> None:
    async with await create_new_container(profile="minimal-python") as c:
        old_id = c.container_id
        await c.reboot(fresh=True)
        assert c.container_id != old_id
        assert await _network_mode(c) == "none"
        assert await _routes(c) == []


@requires_engine
async def test_reboot_fresh_keeps_volume(tmp_path: Path) -> None:
    (tmp_path / "marker.txt").write_text("kept")
    async with await create_new_container(volumes={str(tmp_path): "/mnt/host"}) as c:
        await c.reboot(fresh=True)
        result = await c.run("cat /mnt/host/marker.txt")
        assert result.ok, result.stderr
        assert result.stdout.strip() == "kept"
