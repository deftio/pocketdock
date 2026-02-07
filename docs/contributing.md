# Contributing

See [CONTRIBUTING.md](https://github.com/deftio/pocket-dock/blob/main/CONTRIBUTING.md) for full details.

## Quick Reference

```bash
uv sync --dev                           # Install dependencies
uv run pytest                           # Run tests
uv run ruff check .                     # Lint
uv run ruff format --check .            # Format check
uv run mypy --strict python/pocket_dock/ # Type check
```

## Quality Bar

- 100% line coverage, no exclusions
- Zero ruff warnings
- mypy --strict clean
- bandit clean
- BSD-2-Clause SPDX header in every source file
