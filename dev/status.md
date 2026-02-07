# Implementation Status

Tracking progress against the milestones defined in `plan/pocket-dock-plan.md`.

## Current: Project Scaffold (pre-M0)

- [x] Git repository initialized
- [x] `pyproject.toml` with uv, ruff, mypy, pytest, bandit, coverage config
- [x] `.gitignore`
- [x] `README.md`
- [x] `dev/` directory with this status file
- [x] `.claude/CLAUDE.md`
- [ ] `LICENSE` (BSD-2-Clause)
- [ ] `python/pocket_dock/__init__.py` (empty package)
- [ ] `python/pocket_dock/py.typed` (PEP 561 marker)
- [ ] `tests/` directory
- [ ] `.pre-commit-config.yaml`
- [ ] `.github/workflows/ci.yml`
- [ ] `images/minimal/Dockerfile`
- [ ] `docs/` site with mkdocs-material
- [ ] `examples/` directory
- [ ] `CONTRIBUTING.md`
- [ ] `CHANGELOG.md`
- [ ] First CI-green commit (empty package, all checks pass)

## Milestone Roadmap

| M# | Feature | Version | Status |
|----|---------|---------|--------|
| M0 | Project scaffold + async socket client | 0.1.0 | Not started |
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
