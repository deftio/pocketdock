# Implementation Status

Tracking progress against the milestones defined in `plan/pocket-dock-plan.md`.

## Current: M0 Complete

- [x] Git repository initialized
- [x] `pyproject.toml` with uv, ruff, mypy, pytest, bandit, coverage config
- [x] `.gitignore`
- [x] `README.md`
- [x] `dev/` directory with this status file
- [x] `.claude/CLAUDE.md`
- [x] `LICENSE` (BSD-2-Clause)
- [x] `python/pocket_dock/__init__.py` (exports errors + ExecResult)
- [x] `python/pocket_dock/py.typed` (PEP 561 marker)
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

## Milestone Roadmap

| M# | Feature | Version | Status |
|----|---------|---------|--------|
| M0 | Project scaffold + async socket client | 0.1.0 | **Done** |
| M1 | Blocking run (sync + async facades) | 0.2.0 | Not started |
| M2 | File operations (push/pull via tar) | 0.3.0 | Not started |
| M3 | info() + resource limits | 0.4.0 | Not started |
| M4 | Stream/detach/buffer/callbacks | 0.5.0 | Not started |
| M5 | Sessions (persistent shells) | 0.6.0 | Not started |
| M6 | Persistence (resume, snapshot) | 0.7.0 | Not started |
| M7 | Projects (.pocket-dock/ management) | 0.8.0 | Not started |
| M8 | CLI (15+ commands) | 0.9.0 | Not started |
| M9 | Image profiles | 1.0.0 | Not started |
| M10 | ContainerPool (post-stable) | 1.1.0 | Not started |
