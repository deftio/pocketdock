# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.6.0] - 2026-02-09

### Added

- `AsyncSession` / `Session` — persistent shell sessions with state persistence (cwd, env vars, shell history)
- `session()` method on `AsyncContainer` and `Container` to open a persistent shell
- `send()` — fire-and-forget command to the shell
- `send_and_wait()` — send a command and wait for completion with exit code, stdout, stderr, and duration
- `read()` — drain accumulated output from the session (thread-safe)
- `on_output()` — register callbacks for session output
- `close()` — close the session without stopping the container
- Sentinel protocol (`__PD_{uuid}_${?}__`) for reliable command boundary and exit code detection
- `SessionClosed` error for operations on closed sessions
- `attach_stdin` support in socket client `_exec_create()` for bidirectional exec connections
- Automatic session cleanup during `shutdown()`
- Exported `AsyncSession` from `pocket_dock.async_` and `Session` (alias for `SyncSession`) from `pocket_dock`

## [0.5.0] - 2026-02-08

### Added

- `run(stream=True)` — streaming mode returns `AsyncExecStream` / `ExecStream` async iterator yielding `StreamChunk` objects in real-time
- `run(detach=True)` — detached mode returns `AsyncProcess` / `Process` handle for background execution
- `StreamChunk` dataclass with `stream` ("stdout"/"stderr") and `data` fields
- `AsyncExecStream` / `ExecStream` — async iterator with `.result` property after iteration
- `AsyncProcess` / `Process` — detached process handle with `id`, `is_running()`, `kill()`, `wait()`, `read()`, `peek()`, `buffer_size`, `buffer_overflow`
- `RingBuffer` — thread-safe bounded ring buffer (1 MB default) for detached process output
- `BufferSnapshot` dataclass with `stdout` and `stderr` strings
- `CallbackRegistry` — register callbacks for stdout, stderr, and exit events
- `on_stdout()`, `on_stderr()`, `on_exit()` callback methods on `AsyncContainer` and `Container`
- `demux_stream_iter()` — incremental async generator for stream frame parsing
- `_exec_start_stream()` — streaming exec with Docker chunked TE and Podman raw stream support
- `_demux_chunked_stream()` — handles misalignment between HTTP chunk and demux frame boundaries
- Automatic cleanup of active streams and processes in `shutdown()`
- `@overload` type signatures on `run()` for all three output modes
- Exported `ExecStream`, `Process`, `BufferSnapshot`, `StreamChunk` from `pocket_dock`
- Exported `AsyncExecStream`, `AsyncProcess` from `pocket_dock.async_`

## [0.4.0] - 2026-02-08

### Added

- `info()` — live container snapshot: status, uptime, memory, CPU, PIDs, processes, network
- `reboot()` — restart in place; `reboot(fresh=True)` recreates with same config
- `mem_limit` parameter for `create_new_container()` (e.g. `"256m"`, `"1g"`)
- `cpu_percent` parameter for `create_new_container()` (e.g. `50` for 50% CPU cap)
- `ContainerInfo` dataclass with 15 fields for container introspection
- `get_container_stats()`, `get_container_top()`, `restart_container()` socket client endpoints
- `_helpers.py` module with `format_bytes`, `parse_mem_limit`, `parse_iso_timestamp`, `compute_cpu_percent`
- Resource limits via `HostConfig` (`Memory`, `NanoCpus`) in container creation
- All new methods available on both `AsyncContainer` (async) and `Container` (sync)

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
