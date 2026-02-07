# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.0] - 2026-02-07

### Added

- `write_file()` — write text or binary content into the container via tar archive API
- `read_file()` — read file contents from the container via tar archive API
- `list_files()` — list directory contents inside the container
- `push()` — copy a file or directory from the host into the container
- `pull()` — copy a file or directory from the container to the host
- `push_archive()` and `pull_archive()` in socket client for raw tar transfer
- All methods available on both `AsyncContainer` (async) and `Container` (sync)

## [0.2.0] - 2026-02-07

### Added

- `AsyncContainer` class with async `run()`, `shutdown()`, and context manager
- `Container` class (sync facade) with background event loop thread
- `create_new_container()` factory function (sync in `pocket_dock`, async in `pocket_dock.async_`)
- Blocking `run()` with configurable timeout and output capping
- `lang` parameter for `run()` (e.g. `lang="python"` wraps command with `python3 -c`)
- Timeout support in `exec_command` via `asyncio.wait_for`
- Container labels (`pocket-dock.managed`, `pocket-dock.instance`) for discovery
- Auto-generated container names (`pd-{8 hex}`)
- Multiple independent containers from a single process
- Thread-safe sync facade via `asyncio.run_coroutine_threadsafe`

## [0.1.0] - 2026-02-07

### Added

- Project scaffold: README, CONTRIBUTING, LICENSE (BSD-2-Clause), docs site, CI pipeline
- Async socket client over Unix socket (`_socket_client.py`)
- HTTP/1.1 request/response over Unix domain sockets
- Stream demultiplexing for Docker/Podman exec stream protocol (`_stream.py`)
- Podman and Docker socket auto-detection
- Container lifecycle operations: create, start, stop, remove, inspect
- Exec command with stdout/stderr demux and exit code retrieval
- Error hierarchy: `PocketDockError`, `SocketError`, `ContainerError`, `ImageNotFound`
- `ExecResult` dataclass with `ok` property, timing, and truncation tracking
- Minimal container image Dockerfile (Alpine 3.21 + Python + bash, ~25MB)
- GitHub Actions CI: lint + test matrix (Python 3.10-3.13) + docs + audit
- Pre-commit hooks: ruff, mypy, bandit, check-manifest
- mkdocs-material documentation site
- PEP 561 `py.typed` marker for type checking support
