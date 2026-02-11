# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.1.0] - 2026-02-11

### Changed

- Renamed project from `pocket-dock` to `pocketdock` — package, imports, CLI command, labels, image tags, project directories, and all references
- PyPI package name: `pocketdock` (was `pocket-dock`)
- CLI command: `pocketdock` (was `pocket-dock`)
- Python import: `import pocketdock` (was `import pocket_dock`)
- Image tags: `pocketdock/minimal` etc. (was `pocket-dock/minimal`)
- Project directory: `.pocketdock/` (was `.pocket-dock/`)
- Config file: `pocketdock.yaml` (was `pocket-dock.yaml`)
- Container labels: `pocketdock.*` (was `pocket-dock.*`)

## [1.0.1] - 2026-02-11

### Changed

- Rewrote README as a focused landing page with features list, quick example, and docs links
- Comprehensive docs site with 17 pages: user guide, CLI reference, API reference, concepts
- GitHub Pages deployment via `mkdocs gh-deploy` workflow
- Added `navigation.tabs`, `navigation.top`, and `content.tabs.link` theme features to mkdocs

## [1.0.0] - 2026-02-10

### Added

- Four image profiles: `minimal`, `dev`, `agent`, `embedded` — pre-baked Dockerfiles for common use cases
- `profiles.py` module — `ProfileInfo` dataclass, `resolve_profile()`, `list_profiles()`, `get_dockerfile_path()`
- `profile` parameter on `create_new_container()` — resolves profile name to image tag automatically
- `devices` parameter on `create_new_container()` — USB/device passthrough to containers
- `build_image()`, `save_image()`, `load_image()` socket client methods for image management via engine API
- CLI `build` command — build profile images from Dockerfiles via socket API
- CLI `export` command — save images to tar/tar.gz files for air-gap transfer
- CLI `import` command — load images from tar/tar.gz files
- CLI `profiles` command — list available profiles (table or `--json`)
- `--profile` and `--device` options on CLI `create` command
- Exported `ProfileInfo`, `resolve_profile`, `list_profiles` from `pocketdock` and `pocketdock.async_`

### Changed

- Version bump to 1.0.0 — stable API

## [0.9.0] - 2026-02-10

### Added

- Full CLI with 17 commands: `init`, `list`, `info`, `doctor`, `status`, `logs`, `create`, `run`, `push`, `pull`, `reboot`, `stop`, `resume`, `shutdown`, `snapshot`, `prune`, `shell`
- `stop_container()` — stop a running container by name without removing it (sync and async)
- `--json` flag on read commands (`list`, `info`, `doctor`, `status`, `logs`) for machine-readable output
- `--stream` and `--detach` flags on `run` for streaming and background execution
- `--yes/-y` flag on destructive commands (`shutdown`, `prune`) to skip confirmation prompts
- `--socket` global option and `POCKETDOCK_SOCKET` env var for engine socket override
- Rich-formatted output: tables for container lists, panels for info/doctor, colored success/error messages
- `shell` command — interactive shell via engine CLI passthrough (`podman`/`docker exec -it`)
- Entry point: `pocketdock` (via `pyproject.toml` console script)
- `click` and `rich` CLI dependencies (optional `[cli]` extra)

## [0.8.0] - 2026-02-10

### Added

- `.pocketdock/` project management — `init_project()`, `find_project_root()`, `get_project_name()`
- Instance directory lifecycle — `ensure_instance_dir()`, `write_instance_metadata()`, `read_instance_metadata()`, `remove_instance_dir()`, `list_instance_dirs()`
- `PocketDockConfig` dataclass and `load_config()` with install-level → project-level precedence
- `pocketdock.yaml` project configuration file with logging and persistence defaults
- `instance.toml` metadata files per persistent container (container info, resources, provenance)
- `project` parameter on `create_new_container()` — associates containers with a project
- `pocketdock.project` and `pocketdock.data-path` labels on persistent containers
- `list_containers(project=...)` and `prune(project=...)` — filter by project name
- `destroy_container()` now cleans up the instance directory when `pocketdock.data-path` label is present
- `InstanceLogger` — auto-logging of `run()` results, session I/O, and detached process output to disk
- `history.jsonl` command history per instance
- `doctor()` — cross-references local instance dirs with engine containers to find orphaned containers and stale dirs
- `DoctorReport` dataclass with `orphaned_containers`, `stale_instance_dirs`, `healthy`
- `ProjectNotInitialized` exception
- `PyYAML` and `tomli` (Python < 3.11) added as core dependencies for config/metadata parsing
- All new functions available as sync (from `pocketdock`) and async (from `pocketdock.async_`)

## [0.7.0] - 2026-02-10

### Added

- `persist=True` parameter for `create_new_container()` — container survives `shutdown()` (stop without remove)
- `volumes` parameter for `create_new_container()` — mount host directories into the container
- `container.snapshot(image_name)` — commit container filesystem as a new reusable image
- `container.persist` property — check if container is persistent
- `resume_container(name)` — resume a stopped persistent container by name
- `list_containers()` — list all pocketdock managed containers (running and stopped)
- `destroy_container(name)` — permanently remove a container regardless of persist setting
- `prune()` — remove all stopped pocketdock managed containers
- `ContainerListItem` dataclass with `id`, `name`, `status`, `image`, `created_at`, `persist`
- `pocketdock.persist` and `pocketdock.created-at` labels on all containers
- `list_containers()` and `commit_container()` socket client methods
- All new functions available as sync (from `pocketdock`) and async (from `pocketdock.async_`)

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
- Exported `AsyncSession` from `pocketdock.async_` and `Session` (alias for `SyncSession`) from `pocketdock`

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
- Exported `ExecStream`, `Process`, `BufferSnapshot`, `StreamChunk` from `pocketdock`
- Exported `AsyncExecStream`, `AsyncProcess` from `pocketdock.async_`

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
- `create_new_container()` factory function (sync in `pocketdock`, async in `pocketdock.async_`)
- Blocking `run()` with configurable timeout and output capping
- `lang` parameter for `run()` (e.g. `lang="python"` wraps command with `python3 -c`)
- Timeout support in `exec_command` via `asyncio.wait_for`
- Container labels (`pocketdock.managed`, `pocketdock.instance`) for discovery
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
