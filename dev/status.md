# Implementation Status

Tracking progress against the milestones defined in `plan/pocketdock-plan.md`.

## Current: M2 Complete

### M0 (Done)

- [x] Git repository initialized
- [x] `pyproject.toml` with uv, ruff, mypy, pytest, bandit, coverage config
- [x] `.gitignore`
- [x] `README.md`
- [x] `dev/` directory with this status file
- [x] `.claude/CLAUDE.md`
- [x] `LICENSE` (BSD-2-Clause)
- [x] `python/pocketdock/__init__.py` (exports errors + ExecResult)
- [x] `python/pocketdock/py.typed` (PEP 561 marker)
- [x] `tests/` directory with conftest, import, errors, types, stream, socket client tests
- [x] `.pre-commit-config.yaml`
- [x] `.github/workflows/ci.yml`
- [x] `images/minimal/Dockerfile`
- [x] `docs/` site with mkdocs-material
- [x] `examples/` directory
- [x] `CONTRIBUTING.md`
- [x] `CHANGELOG.md`
- [x] Error hierarchy (`errors.py`)
- [x] ExecResult type (`types.py`)
- [x] Stream demux (`_stream.py`)
- [x] Async socket client (`_socket_client.py`)
- [x] All linting passes (ruff, mypy --strict, bandit)
- [x] Unit tests pass locally; integration tests skip without Podman

### M1 (Done)

- [x] `AsyncContainer` class (`_async_container.py`) with `run()`, `shutdown()`, context manager
- [x] `Container` sync facade (`_sync_container.py`) with background event loop thread
- [x] `create_new_container()` factory (sync in `__init__.py`, async in `async_.py`)
- [x] Blocking `run()` with timeout and output capping
- [x] `lang` parameter for `run()` (e.g. `lang="python"`)
- [x] Timeout support in `exec_command` via `asyncio.wait_for`
- [x] Container labels (`pocketdock.managed`, `pocketdock.instance`)
- [x] Auto-generated container names (`pd-{8 hex}`)
- [x] Multiple containers from one process work independently
- [x] Thread-safe sync facade via `asyncio.run_coroutine_threadsafe`
- [x] Integration tests: async/sync lifecycle, run, timeout, truncation, concurrent, multi-container
- [x] Unit tests: name gen, command build, properties, run/shutdown delegation, error paths, imports
- [x] All linting passes (ruff, mypy --strict, bandit)

### M2 (Done)

- [x] `push_archive()` and `pull_archive()` in `_socket_client.py` for raw tar transfer
- [x] `write_file()` — write text or binary content into the container
- [x] `read_file()` — read file contents from the container
- [x] `list_files()` — list directory contents inside the container
- [x] `push()` — copy file/directory from host into the container
- [x] `pull()` — copy file/directory from the container to the host
- [x] Sync wrappers for all file operations in `Container`
- [x] Integration tests: async + sync write/read, binary, nested paths, push/pull files/dirs, error paths
- [x] Unit tests: tar packing/unpacking, mock-based delegation, error paths
- [x] All linting passes (ruff, mypy --strict, bandit)

## Milestone Roadmap

| M# | Feature | Version | Status |
|----|---------|---------|--------|
| M0 | Project scaffold + async socket client | 0.1.0 | **Done** |
| M1 | Blocking run (sync + async facades) | 0.2.0 | **Done** |
| M2 | File operations (push/pull via tar) | 0.3.0 | **Done** |
| M3 | info() + resource limits | 0.4.0 | Not started |
| M4 | Stream/detach/buffer/callbacks | 0.5.0 | Not started |
| M5 | Sessions (persistent shells) | 0.6.0 | Not started |
| M6 | Persistence (resume, snapshot) | 0.7.0 | Not started |
| M7 | Projects (.pocketdock/ management) | 0.8.0 | Not started |
| M8 | CLI (15+ commands) | 0.9.0 | Not started |
| M9 | Image profiles | 1.0.0 | Not started |
| M10 | ContainerPool (post-stable) | 1.1.0 | Not started |
