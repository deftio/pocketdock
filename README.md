# pocket-dock

**Portable, offline-first container sandboxes for LLM agents and dev workflows.**

One `Container` class. Podman-first, Docker-compatible. Python SDK + CLI. Zero external dependencies. Zero API keys. Zero cloud.

## What is this?

pocket-dock is a thin, reusable Python library that talks directly to your container engine over its Unix socket. It ships with pre-baked images you build once and keep locally, and works entirely offline after initial setup.

**Use cases:**
- LLM agents that need to execute code in isolation
- Reproducible embedded dev environments (C/C++ toolchains)
- Code evaluation pipelines
- Any workflow that needs container sandboxes without cloud dependencies

## Quick start

```bash
# Install
pip install pocket-dock

# Requires Podman (recommended) or Docker
# Podman: https://podman.io/getting-started/installation
# Docker: https://docs.docker.com/get-docker/

# Build the minimal image (~25MB)
podman build -t pocket-dock/minimal images/minimal/

# Use from Python
from pocket_dock import create_new_container

c = create_new_container()
result = c.run("echo hello")
print(result.stdout)  # "hello\n"
c.shutdown()
```

## Features

- **Offline-first** — after initial image build, everything works without internet
- **Zero SDK dependencies** — stdlib-only socket client, no docker-py or podman-py
- **Podman-first, Docker-compatible** — same REST API, same socket protocol
- **Sync and async** — `c.run()` or `await c.run()`
- **Three output modes** — blocking, streaming, detached
- **Sessions** — persistent shell connections with state across commands
- **Project-rooted** — instance data lives in `.pocket-dock/` next to your code
- **Pre-baked image profiles** — minimal, dev, agent, embedded (C/C++ toolchains)

## Status

This project is under active development. See `plan/pocket-dock-plan.md` for the full architecture spec and `dev/status.md` for current implementation progress.

## License

BSD-2-Clause. Copyright (c) deftio llc.
