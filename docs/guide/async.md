# Async API

pocket-dock is async-first. The sync `Container` is a thin facade over `AsyncContainer`, which does all real work. Use the async API directly when you need concurrency or are already in an async context.

## Import

```python
from pocket_dock.async_ import create_new_container
```

All async equivalents live in `pocket_dock.async_`:

```python
from pocket_dock.async_ import (
    create_new_container,
    resume_container,
    list_containers,
    destroy_container,
    stop_container,
    prune,
    doctor,
    find_project_root,
    init_project,
    resolve_profile,
    list_profiles,
)
```

## Basic Usage

```python
import asyncio
from pocket_dock.async_ import create_new_container

async def main():
    async with await create_new_container() as c:
        result = await c.run("echo hello")
        print(result.stdout)

asyncio.run(main())
```

!!! note
    `create_new_container()` returns an awaitable. Use `await` to get the container, then `async with` for automatic cleanup.

## Concurrent Containers

Run commands in multiple containers simultaneously:

```python
import asyncio
from pocket_dock.async_ import create_new_container

async def main():
    async with (
        await create_new_container() as c1,
        await create_new_container() as c2,
    ):
        r1, r2 = await asyncio.gather(
            c1.run("sleep 2 && echo done-1"),
            c2.run("sleep 2 && echo done-2"),
        )
        # Takes ~2 seconds total, not ~4
        print(r1.stdout)  # "done-1\n"
        print(r2.stdout)  # "done-2\n"

asyncio.run(main())
```

## Streaming (Async)

```python
async with await create_new_container() as c:
    async for chunk in await c.run("make all", stream=True):
        print(chunk.data, end="")
```

The async stream is an `AsyncExecStream` — an async iterator of `StreamChunk` objects.

## Detached (Async)

```python
async with await create_new_container() as c:
    proc = await c.run("python server.py", detach=True)
    await asyncio.sleep(1)
    print(await proc.is_running())  # True
    output = proc.peek()
    print(output.stdout)
    await proc.kill()
```

## Sessions (Async)

```python
async with await create_new_container() as c:
    sess = await c.session()
    await sess.send("cd /tmp")
    result = await sess.send_and_wait("pwd")
    print(result.stdout)  # "/tmp\n"
    await sess.close()
```

## When to Use Async vs Sync

| Scenario | Recommendation |
|----------|---------------|
| Scripts, CLIs, notebooks | Use sync (`pocket_dock`) |
| Already in an async context | Use async (`pocket_dock.async_`) |
| Multiple containers concurrently | Use async + `asyncio.gather()` |
| Web frameworks (FastAPI, aiohttp) | Use async |
| Simple one-container tasks | Use sync |

## Async Types

The async API uses different type names for streams and processes:

| Sync | Async |
|------|-------|
| `ExecStream` | `AsyncExecStream` |
| `Process` | `AsyncProcess` |
| `Session` | `AsyncSession` |

These are exported from `pocket_dock.async_`:

```python
from pocket_dock.async_ import AsyncContainer, AsyncExecStream, AsyncProcess, AsyncSession
```

## How the Sync Facade Works

The sync `Container` class manages a background thread with its own event loop. Every sync method call is forwarded to the async method via `asyncio.run_coroutine_threadsafe()`. This means:

- You can use the sync API from any thread
- Multiple sync containers share a single background event loop
- The sync API has minimal overhead beyond the thread hop
