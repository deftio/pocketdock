# Contributing to pocket-dock

## Development Setup

```bash
# Clone the repo
git clone https://github.com/deftio/pocket-dock.git
cd pocket-dock

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all dependencies
uv sync --dev

# Install pre-commit hooks
uv run pre-commit install
```

## Quality Bar

Every commit must pass:

- **100% line coverage** — no `# pragma: no cover`, no exclusions
- **Zero ruff warnings** — `select = ["ALL"]`, `ignore = ["D1"]`
- **mypy --strict clean** — every function has type annotations
- **bandit clean** — security linting for socket/file/tar operations
- **BSD-2-Clause SPDX header** in every `.py` source file under `python/pocket_dock/`

## Running Checks

```bash
uv run ruff check .                                 # Lint
uv run ruff format --check .                        # Format check
uv run mypy --strict python/pocket_dock/            # Type check
uv run bandit -r python/pocket_dock/ -c pyproject.toml  # Security lint
uv run pytest                                       # Tests (100% coverage)
```

## Test Strategy

All tests are integration tests against a real Podman socket. No mocks.

- Tests skip gracefully if no Podman socket is found locally
- CI always has Podman available — all tests must pass there
- Use the `minimal` profile (~25MB, <500ms startup) for tests

## Git Workflow

- **Branch naming**: `{type}/{description}` — e.g., `feat/m1-blocking-run`, `fix/stream-demux`
- **Commit messages**: Conventional prefix — `feat:`, `fix:`, `test:`, `docs:`, `ci:`, `refactor:`
- **Development cycle**: TDD — write tests first, red, implement, green, full lint suite, doc sync, PR

## License

By contributing, you agree that your contributions will be licensed under the BSD-2-Clause license.
