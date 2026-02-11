# pocket-dock

[![CI](https://github.com/deftio/pocket-dock/actions/workflows/ci.yml/badge.svg)](https://github.com/deftio/pocket-dock/actions/workflows/ci.yml)
[![Coverage: 100%](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)](https://github.com/deftio/pocket-dock/actions/workflows/ci.yml)
[![License: BSD-2-Clause](https://img.shields.io/badge/License-BSD_2--Clause-blue.svg)](https://opensource.org/licenses/BSD-2-Clause)

**Portable, offline-first container sandboxes for LLM agents and dev workflows.**

One Container class. Podman-first, Docker-compatible. Python SDK + CLI. Minimal dependencies. Zero API keys. Zero cloud.

## Why pocket-dock?

Managed sandbox platforms (E2B, Daytona) require API keys, cloud accounts, paid tiers, and an internet connection. Rolling your own container glue means rewriting ~200 lines of boilerplate every time. pocket-dock sits in between: a clean Python SDK that talks directly to your container engine over its Unix socket, works entirely offline after initial setup, and has zero external dependencies.

**Use cases:**
- **LLM agent code execution** — run untrusted code in isolated sandboxes with resource limits
- **Code evaluation pipelines** — evaluate student/candidate code safely with timeouts and output caps
- **Embedded development** — C/C++ cross-compilation for ARM, ESP32, Arduino inside containers
- **Reproducible dev environments** — disposable sandboxes with pre-baked toolchains
- **CI/CD building blocks** — lightweight, scriptable container orchestration

## Quick start

```bash
# Install
pip install pocket-dock

# Requires Podman (recommended) or Docker
# Podman: https://podman.io/getting-started/installation
# Docker: https://docs.docker.com/get-docker/

# Build the minimal image (~25MB, <500ms startup)
podman build -t pocket-dock/minimal images/minimal/
```

```python
from pocket_dock import create_new_container

# Create an isolated container
with create_new_container() as c:
    result = c.run("echo hello")
    print(result.stdout)  # "hello\n"
    print(result.ok)      # True
# Container is automatically stopped and removed
```

## SDK

### Three output modes

**Blocking** (default) — run a command, wait for it to finish, get all output at once:

```python
result = c.run("echo hello")
result.exit_code   # 0
result.stdout      # "hello\n"
result.stderr      # ""
result.ok          # True
result.duration_ms # 47

# Python code
result = c.run("print(2 + 2)", lang="python")

# Timeout and output cap
result = c.run("make -j$(nproc)", timeout=300, max_output=1_000_000)
```

**Streaming** — yield output chunks as they arrive, for builds and long-running scripts:

```python
for chunk in c.run("make all 2>&1", stream=True):
    print(chunk.data, end="")
    # chunk.stream is "stdout" or "stderr"
```

**Detached** — start a background process and get a handle to monitor or kill it:

```python
proc = c.run("python -m http.server 8080", detach=True)
proc.is_running()  # True

# Read buffered output without blocking
output = proc.peek()
print(output.stdout)

# Wait for completion
result = proc.wait(timeout=60)

# Or kill it
proc.kill()
```

### File operations

```python
# Write a file into the container
c.write_file("/home/sandbox/config.json", '{"debug": true}')

# Read a file from the container
data = c.read_file("/home/sandbox/output.txt")

# List a directory
files = c.list_files("/home/sandbox/")

# Copy files between host and container
c.push("./local_script.py", "/home/sandbox/script.py")
c.pull("/home/sandbox/results.csv", "./results.csv")

# Push entire directories
c.push("./src/", "/home/sandbox/src/")
```

### Resource limits and container info

```python
c = create_new_container(mem_limit="256m", cpu_percent=50)

info = c.info()
info.status          # "running"
info.memory_usage    # "42.1 MB"
info.memory_limit    # "256 MB"
info.cpu_percent     # 3.2
info.pids            # 2
info.network         # True
info.ip_address      # "172.17.0.2"
```

### Callbacks

Register callbacks for detached processes to monitor output and exit events:

```python
c.on_stdout(lambda container, data: print(f"[stdout] {data}", end=""))
c.on_stderr(lambda container, data: print(f"[stderr] {data}", end=""))
c.on_exit(lambda container, code: print(f"Process exited with code {code}"))

proc = c.run("python long_task.py", detach=True)
```

### Async API

The sync `Container` is a thin facade over `AsyncContainer`. Use the async API directly for concurrent operations:

```python
from pocket_dock.async_ import create_new_container
import asyncio

async def main():
    async with await create_new_container() as c1, await create_new_container() as c2:
        # Run in both containers simultaneously
        r1, r2 = await asyncio.gather(
            c1.run("sleep 2 && echo done-1"),
            c2.run("sleep 2 && echo done-2"),
        )
        # Takes ~2 seconds total, not ~4

asyncio.run(main())
```

## CLI

pocket-dock includes a full CLI for managing containers from the terminal:

```bash
pip install pocket-dock[cli]

# Project management
pocket-dock init                            # initialize a .pocket-dock/ project
pocket-dock status                          # project summary and container states
pocket-dock doctor                          # diagnose orphaned containers / stale dirs

# Container lifecycle
pocket-dock create --image alpine --name my-sandbox
pocket-dock run my-sandbox echo hello
pocket-dock run my-sandbox --stream make all
pocket-dock run my-sandbox --detach python server.py
pocket-dock shell my-sandbox                # interactive shell

# File operations
pocket-dock push my-sandbox ./src/ /home/sandbox/src/
pocket-dock pull my-sandbox /home/sandbox/output.csv ./output.csv

# Container management
pocket-dock list                            # list all containers
pocket-dock list --json                     # machine-readable output
pocket-dock info my-sandbox                 # detailed container info
pocket-dock logs                            # command history
pocket-dock reboot my-sandbox               # restart in place
pocket-dock stop my-sandbox                 # stop without removing
pocket-dock resume my-sandbox               # resume stopped container
pocket-dock snapshot my-sandbox my-image:v1 # commit as image
pocket-dock shutdown my-sandbox --yes       # stop + remove
pocket-dock prune --yes                     # remove all stopped containers
```

## Image profiles

Four pre-baked Dockerfiles ship in `images/` for common use cases:

| Profile | Size | Base | Contents | Default network |
|---------|------|------|----------|-----------------|
| **minimal** | ~25 MB | Alpine 3.21 | Python 3, pip, bash | Disabled |
| **dev** | ~250 MB | python:3.12-slim | Git, curl, jq, vim, build tools, ipython | Enabled |
| **agent** | ~350 MB | python:3.12-slim | requests, pandas, numpy, beautifulsoup4, pillow | Disabled |
| **embedded** | ~450 MB | Alpine 3.21 | GCC, CMake, ARM cross-compiler, Arduino CLI, PlatformIO | Enabled |

```bash
# Build all profiles
for p in minimal dev agent embedded; do
    podman build -t pocket-dock/$p images/$p/
done
```

## Architecture

```
User Code / LLM Agent / CLI
        |
        v
  pocket-dock SDK
  +--------------------------------------+
  | Container (sync)  -> AsyncContainer  |  facade pattern
  |   +- _socket_client (raw HTTP/Unix)  |
  +- ProjectManager (.pocket-dock/)      |
  +- Persistence (resume, snapshot)      |
  +- Sessions (persistent shells)        |
  +- ContainerPool (pre-warming)         |
  +--------------------------------------+
        |  raw HTTP over Unix socket
        |  (one connection per operation)
        v
  Podman (rootless) / Docker Engine
```

**Design principles:**
- **Connection-per-operation** — each API call opens its own Unix socket connection. No pooling. Unix sockets are cheap; isolation prevents streaming from blocking other operations.
- **Async core, sync facade** — `AsyncContainer` does all real work. `Container` is a sync wrapper that manages a background event loop.
- **No cached state** — always poll live from the engine. The container might have been killed externally.
- **Minimal dependencies** — the SDK uses Python stdlib for container I/O, plus `PyYAML` and `tomli` for config/metadata parsing.

## Roadmap

| Milestone | Feature | Version | Status |
|-----------|---------|---------|--------|
| M0 | Socket client | 0.1.0 | Done |
| M1 | Blocking run (sync + async) | 0.2.0 | Done |
| M2 | File operations (push/pull) | 0.3.0 | Done |
| M3 | Container info + resource limits | 0.4.0 | Done |
| M4 | Stream / detach / buffer / callbacks | 0.5.0 | Done |
| M5 | Sessions (persistent shells) | 0.6.0 | Done |
| M6 | Persistence (resume, snapshot) | 0.7.0 | Done |
| M7 | Projects (.pocket-dock/ management) | 0.8.0 | Done |
| M8 | CLI (17 commands) | 0.9.0 | Done |
| M9 | Image profiles | 1.0.0 | Planned |
| M10 | ContainerPool (pre-warming) | 1.1.0 | Planned |

See `plan/pocket-dock-plan.md` for the full 2500-line architecture spec.

## Development

```bash
uv sync --dev                    # Install dependencies
uv run pytest                    # Run tests (100% coverage enforced)
uv run ruff check .              # Lint (zero warnings)
uv run mypy --strict python/     # Type checking (strict mode)
```

## License

BSD-2-Clause. Copyright (c) deftio llc.
