# pocket-dock

**Portable, offline-first container sandboxes for LLM agents and dev workflows.**

One `Container` class. Podman-first, Docker-compatible. Python SDK + CLI. Zero external dependencies.

## What is this?

pocket-dock is a thin, reusable Python library that talks directly to your container engine over its Unix socket. It ships with pre-baked images you build once and keep locally, and works entirely offline after initial setup.

## Quick start

```bash
pip install pocket-dock
podman build -t pocket-dock/minimal images/minimal/
```

```python
from pocket_dock import create_new_container

c = create_new_container()
result = c.run("echo hello")
print(result.stdout)  # "hello\n"
c.shutdown()
```

## Status

This project is under active development. See the [Quickstart](quickstart.md) to get started.
