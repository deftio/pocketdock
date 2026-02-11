# pocket-dock

[![CI](https://github.com/deftio/pocket-dock/actions/workflows/ci.yml/badge.svg)](https://github.com/deftio/pocket-dock/actions/workflows/ci.yml)
[![Coverage: 100%](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)](https://github.com/deftio/pocket-dock/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-deftio.github.io%2Fpocket--dock-blue)](https://deftio.github.io/pocket-dock/)
[![License: BSD-2-Clause](https://img.shields.io/badge/License-BSD_2--Clause-blue.svg)](https://opensource.org/licenses/BSD-2-Clause)

**Portable, offline-first container sandboxes for LLM agents and dev workflows.**

One Container class. Podman-first, Docker-compatible. Python SDK + CLI. Zero cloud. Zero API keys.

## Why pocket-dock?

Managed sandbox platforms require API keys, cloud accounts, and an internet connection. Rolling your own container glue means rewriting hundreds of lines of boilerplate every time. pocket-dock sits in between: a clean Python SDK that talks directly to your container engine over its Unix socket, works entirely offline, and has zero external dependencies for the core SDK.

## Features

- **Three execution modes** — blocking, streaming, and detached (background) with ring buffer
- **File operations** — read, write, list, push, and pull files between host and container
- **Persistent sessions** — long-lived shell sessions with state (cwd, env vars, history)
- **Resource limits** — memory caps, CPU throttling, per-container isolation
- **Container persistence** — stop/resume, snapshot to image, volume mounts
- **Project management** — `.pocket-dock/` project directories with config, logging, and health checks
- **Image profiles** — four pre-baked Dockerfiles: minimal, dev, agent, embedded
- **Full CLI** — 21 commands for container lifecycle, file ops, and project management
- **Async-first** — sync facade over async core; use either API style
- **Callbacks** — register handlers for stdout, stderr, and exit events

## Quick Example

```python
from pocket_dock import create_new_container

with create_new_container() as c:
    result = c.run("echo hello")
    print(result.stdout)  # "hello\n"
    print(result.ok)      # True
```

## Install

```bash
pip install pocket-dock          # SDK only (zero dependencies)
pip install pocket-dock[cli]     # SDK + CLI (click, rich)
```

Requires [Podman](https://podman.io/getting-started/installation) (recommended) or [Docker](https://docs.docker.com/get-docker/).

```bash
# Build the minimal image (~25MB, <500ms startup)
pocket-dock build minimal
```

## Documentation

Full documentation is available at **[deftio.github.io/pocket-dock](https://deftio.github.io/pocket-dock/)**.

- [Quickstart](https://deftio.github.io/pocket-dock/quickstart/) — install, build, run your first container
- [User Guide](https://deftio.github.io/pocket-dock/guide/containers/) — containers, commands, files, sessions, persistence, profiles
- [CLI Reference](https://deftio.github.io/pocket-dock/cli/) — all 21 commands with examples
- [API Reference](https://deftio.github.io/pocket-dock/reference/api/) — full SDK reference

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
  +--------------------------------------+
        |  raw HTTP over Unix socket
        |  (one connection per operation)
        v
  Podman (rootless) / Docker Engine
```

**Design principles:**

- **Connection-per-operation** — each API call opens its own Unix socket. No pooling.
- **Async core, sync facade** — `AsyncContainer` does all real work. `Container` is a sync wrapper.
- **No cached state** — always polls live from the engine.
- **Minimal dependencies** — stdlib-only for the core SDK.

## Development

```bash
uv sync --dev                    # Install dependencies
uv run pytest                    # Run tests (100% coverage enforced)
uv run ruff check .              # Lint (zero warnings)
uv run mypy --strict python/     # Type checking (strict mode)
uv run mkdocs serve              # Local docs site
```

## License

BSD-2-Clause. Copyright (c) deftio llc.
