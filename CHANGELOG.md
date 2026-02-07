# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
