"""Integration tests for multi-container independence."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from pocketdock import create_new_container
from pocketdock._async_container import create_new_container as async_create
from pocketdock.errors import ContainerNotFound, ContainerNotRunning

from .conftest import requires_engine

# --- Async: multiple containers via asyncio.gather ---


@requires_engine
async def test_async_multi_container() -> None:
    c1 = await async_create()
    c2 = await async_create()
    try:
        r1, r2 = await asyncio.gather(
            c1.run("echo one"),
            c2.run("echo two"),
        )
        assert r1.stdout.strip() == "one"
        assert r2.stdout.strip() == "two"
    finally:
        await c1.shutdown()
        await c2.shutdown()


@requires_engine
async def test_async_one_dying_no_affect() -> None:
    """One container being removed doesn't affect the other."""
    c1 = await async_create()
    c2 = await async_create()
    try:
        await c1.shutdown(force=True)
        result = await c2.run("echo still-alive")
        assert result.ok
        assert result.stdout.strip() == "still-alive"
    finally:
        await c2.shutdown()


# --- Sync: multiple containers via threads ---


@requires_engine
def test_sync_multi_container() -> None:
    c1 = create_new_container()
    c2 = create_new_container()
    try:
        r1 = c1.run("echo alpha")
        r2 = c2.run("echo bravo")
        assert r1.stdout.strip() == "alpha"
        assert r2.stdout.strip() == "bravo"
    finally:
        c1.shutdown()
        c2.shutdown()


@requires_engine
def test_sync_thread_pool() -> None:
    containers = [create_new_container() for _ in range(3)]
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(c.run, f"echo {i}") for i, c in enumerate(containers)]
            results = [f.result() for f in futures]
        for r in results:
            assert r.ok
        outputs = sorted(r.stdout.strip() for r in results)
        assert outputs == ["0", "1", "2"]
    finally:
        for c in containers:
            c.shutdown()


@requires_engine
def test_sync_one_dying_no_affect() -> None:
    c1 = create_new_container()
    c2 = create_new_container()
    try:
        c1.shutdown(force=True)
        result = c2.run("echo ok")
        assert result.ok
        assert result.stdout.strip() == "ok"
    finally:
        c2.shutdown()


# --- Error: run on shutdown container ---


@requires_engine
def test_run_after_shutdown_raises() -> None:
    c = create_new_container()
    c.shutdown()
    try:
        c.run("echo fail")
    except (ContainerNotFound, ContainerNotRunning):
        pass
    else:
        msg = "Expected ContainerNotFound or ContainerNotRunning"
        raise AssertionError(msg)
