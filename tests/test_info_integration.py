"""Integration tests for info(), reboot(), and resource limits."""

from __future__ import annotations

from pocket_dock._async_container import create_new_container
from pocket_dock.types import ContainerInfo

from .conftest import requires_engine

# --- info() ---


@requires_engine
async def test_info_running_container() -> None:
    async with await create_new_container() as c:
        info = await c.info()
        assert isinstance(info, ContainerInfo)
        assert info.status == "running"
        assert info.id == c.container_id
        assert info.name == c.name
        assert info.created_at is not None
        assert info.started_at is not None
        assert info.uptime is not None
        assert info.uptime.total_seconds() >= 0


@requires_engine
async def test_info_has_image() -> None:
    async with await create_new_container() as c:
        info = await c.info()
        # Image should be set (engine may resolve to full ref)
        assert info.image


@requires_engine
async def test_info_has_pids() -> None:
    async with await create_new_container() as c:
        info = await c.info()
        # At minimum, the sleep process should be running
        assert info.pids >= 1


@requires_engine
async def test_info_has_memory() -> None:
    async with await create_new_container() as c:
        info = await c.info()
        # Running container should report some memory usage
        assert info.memory_usage  # non-empty string


@requires_engine
async def test_info_has_processes() -> None:
    async with await create_new_container() as c:
        info = await c.info()
        assert len(info.processes) >= 1


# --- reboot() ---


@requires_engine
async def test_reboot_preserves_container() -> None:
    async with await create_new_container() as c:
        old_id = c.container_id
        # Write a file, reboot, verify it's still there
        await c.run("touch /tmp/marker")
        await c.reboot()
        result = await c.run("ls /tmp/marker")
        assert result.ok
        assert c.container_id == old_id  # same container


@requires_engine
async def test_reboot_fresh_creates_new_container() -> None:
    c = await create_new_container()
    try:
        old_id = c.container_id
        await c.run("touch /tmp/marker")
        await c.reboot(fresh=True)
        assert c.container_id != old_id
        # Marker file should be gone in fresh container
        result = await c.run("ls /tmp/marker 2>/dev/null || echo 'gone'")
        assert "gone" in result.stdout
    finally:
        await c.shutdown()


# --- Resource limits ---


@requires_engine
async def test_create_with_mem_limit() -> None:
    async with await create_new_container(mem_limit="128m") as c:
        info = await c.info()
        assert info.memory_limit  # should be non-empty
        # The limit should reflect ~128MB (engines may report slightly different)


@requires_engine
async def test_create_with_cpu_percent() -> None:
    async with await create_new_container(cpu_percent=50) as c:
        # Container should be running
        info = await c.info()
        assert info.status == "running"


@requires_engine
async def test_create_with_both_limits() -> None:
    async with await create_new_container(mem_limit="64m", cpu_percent=25) as c:
        info = await c.info()
        assert info.status == "running"
        assert info.memory_limit


# --- info() on stopped container ---


@requires_engine
async def test_info_after_stop() -> None:
    c = await create_new_container()
    try:
        from pocket_dock import _socket_client as sc

        await sc.stop_container(c.socket_path, c.container_id)
        info = await c.info()
        assert info.status == "exited"
        # Stats should be empty for a stopped container
        assert info.memory_usage == ""
        assert info.pids == 0
    finally:
        await c.shutdown()


# --- reboot(fresh=True) inherits resource limits ---


@requires_engine
async def test_reboot_fresh_preserves_limits() -> None:
    c = await create_new_container(mem_limit="128m")
    try:
        old_id = c.container_id
        await c.reboot(fresh=True)
        assert c.container_id != old_id
        info = await c.info()
        assert info.status == "running"
        assert info.memory_limit  # limits should still apply
    finally:
        await c.shutdown()


# --- Sync Container info/reboot (quick smoke test) ---


@requires_engine
def test_sync_info() -> None:
    from pocket_dock import create_new_container as sync_create

    with sync_create() as c:
        info = c.info()
        assert isinstance(info, ContainerInfo)
        assert info.status == "running"


@requires_engine
def test_sync_reboot() -> None:
    from pocket_dock import create_new_container as sync_create

    with sync_create() as c:
        old_id = c.container_id
        c.reboot()
        assert c.container_id == old_id  # same container, just restarted
        result = c.run("echo alive")
        assert result.ok
