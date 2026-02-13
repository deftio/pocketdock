# Contributing to pocketdock

## Development Setup

```bash
# Clone the repo
git clone https://github.com/deftio/pocketdock.git
cd pocketdock

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
- **BSD-2-Clause SPDX header** in every `.py` source file under `python/pocketdock/`

## Running Checks

```bash
uv run ruff check .                                 # Lint
uv run ruff format --check .                        # Format check
uv run mypy --strict python/pocketdock/            # Type check
uv run bandit -r python/pocketdock/ -c pyproject.toml  # Security lint
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

## Feature Commit Checklist

Every feature branch must complete **all** of these steps before merging. See `plan/checklist.md` for the full version with checkboxes.

### 1. Branch

Create a focused branch from `main` — one feature or fix per branch.

### 2. Write Tests First (TDD)

- Write tests **before** implementation
- Cover the golden path, edge cases, error paths, and cleanup
- Integration tests run against real Podman (no mocks)
- Run tests — they must **fail** (red) before you write code

### 3. Implement

- Make the tests pass (green)
- Type annotations on every new function
- BSD-2-Clause SPDX header on every new `.py` file

### 4. Quality Gate

All must be green — zero exceptions:

```bash
uv run ruff check .                                    # lint
uv run ruff format --check .                           # format
uv run mypy --strict python/pocketdock/               # types
uv run bandit -r python/pocketdock/ -c pyproject.toml  # security
uv run pytest                                          # tests + 100% coverage
```

### 5. Docs Sync

This is a content review, not just a build step. Read the affected pages.

- **README.md** — still matches current API and behavior?
- **Affected docs/ pages** — guides, reference, concepts updated?
- **CHANGELOG.md** — entry added under `[Unreleased]` (or the current version)
- **Examples** — affected SDK/CLI examples still run?
- **License headers** — all new `.py` files have the SPDX header

```bash
uv run mkdocs build --strict    # catch broken links / missing pages
```

### 6. Final Check

Run the full suite **again** after doc changes:

```bash
uv run pre-commit run --all-files && uv run pytest
```

### 7. Ship

- Push branch and open PR
- CI must pass (lint + test matrix 3.10–3.13 + audit + docs build)
- Merge to `main`

## Release Flow

After merging a version bump to `main`:

1. **Verify CI passes on `main`** — all jobs green (lint, test matrix, docs, audit)
2. **Confirm GitHub Pages deployed** — the `docs` job in CI builds and deploys to Pages on every push to `main`
3. **Tag the release**:
   ```bash
   git checkout main && git pull
   git tag -a v{X.Y.Z} -m "description"
   git push origin v{X.Y.Z}
   ```
4. **Create a GitHub release** from the tag — this triggers the `publish.yml` workflow which builds and publishes to PyPI via trusted publishing
5. **Verify PyPI** — confirm the new version appears at https://pypi.org/project/pocketdock/

The publish workflow (`publish.yml`) runs automatically on `release: published` events. Do **not** manually upload to PyPI.

### Version Bumping

- Update `version` in `pyproject.toml`
- Add a dated entry in `CHANGELOG.md`
- Commit as `chore: bump version to {X.Y.Z}`
- Follow [Semantic Versioning](https://semver.org/): breaking = major, feature = minor, fix = patch

## License

By contributing, you agree that your contributions will be licensed under the BSD-2-Clause license.
