# pocketdock

**Portable, offline-first container sandboxes for LLM agents and dev workflows.**

pocketdock is a Python SDK and CLI that talks directly to Podman or Docker over its Unix socket. No cloud. No API keys. No external dependencies for the core SDK.

---

## Use Cases

- **LLM agent code execution** — run untrusted code in isolated sandboxes with resource limits
- **Code evaluation pipelines** — evaluate student/candidate code safely with timeouts and output caps
- **Embedded development** — C/C++ cross-compilation for ARM, ESP32, Arduino inside containers
- **Reproducible dev environments** — disposable sandboxes with pre-baked toolchains
- **CI/CD building blocks** — lightweight, scriptable container orchestration

## Feature Highlights

| Feature | Description |
|---------|-------------|
| **Three execution modes** | Blocking, streaming, and detached with ring buffer |
| **File operations** | Read, write, list, push, pull between host and container |
| **Persistent sessions** | Long-lived shells with state (cwd, env vars, history) |
| **Resource limits** | Memory caps and CPU throttling per container |
| **Persistence** | Stop/resume containers, snapshot to images, volume mounts |
| **Project management** | `.pocketdock/` directories with config, logging, health checks |
| **Image profiles** | Six pre-baked Dockerfiles: minimal-python, minimal-node, minimal-bun, dev, agent, embedded |
| **Full CLI** | 22 commands for lifecycle, file ops, and project management |
| **Async-first** | Sync facade over async core — use either API |
| **Callbacks** | Register handlers for stdout, stderr, and exit events |

## Quick Example

```python
from pocketdock import create_new_container

with create_new_container() as c:
    # Run a command
    result = c.run("echo hello")
    print(result.stdout)  # "hello\n"
    print(result.ok)      # True

    # Run Python code
    result = c.run("print(2 + 2)", lang="python")
    print(result.stdout)  # "4\n"

    # Read/write files
    c.write_file("/tmp/data.txt", "hello from host")
    data = c.read_file("/tmp/data.txt")
# Container is automatically stopped and removed
```

## Install

=== "Standard"

    ```bash
    pip install pocketdock
    ```

=== "With LLM Agent"

    ```bash
    pip install pocketdock[agent]
    ```

Single-file downloads (no pip required) are available from [GitHub Releases](https://github.com/deftio/pocketdock/releases).

Requires [Podman](https://podman.io/getting-started/installation) (recommended) or [Docker](https://docs.docker.com/get-docker/).

## What's Next?

- **[Quickstart](quickstart.md)** — build an image and run your first container in under a minute
- **[User Guide](guide/containers.md)** — deep dive into containers, commands, files, sessions, and more
- **[CLI Reference](cli.md)** — all 22 commands with examples
- **[API Reference](reference/api.md)** — full SDK reference with type signatures
