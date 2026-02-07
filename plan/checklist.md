# Feature Commit Checklist

> **This document lives at `plan/checklist.md` in the repo.** Pin it, run it for every feature branch. No exceptions.



## Branch

- [ ] Create branch from `main`: `feat/m{N}-{description}` (e.g. `feat/m2-file-operations`)
- [ ] Branch is focused — one feature or fix, not a grab bag

## Write Tests First (TDD)

- [ ] Write test cases for the new behavior **before** writing implementation
- [ ] Tests cover the **golden path** — the expected, normal-use scenario works end to end
- [ ] Tests cover **edge cases** — empty input, boundary values, max sizes, zero-length, Unicode
- [ ] Tests cover **error paths** — bad input, timeouts, missing resources, container not running
- [ ] Tests cover **cleanup** — resources are released on success, failure, and exception
- [ ] Tests run against **real Podman** (no mocks, no fakes, no stubs)
- [ ] Run tests — they **fail** (red). If they pass before you write code, they're testing nothing.

## Implement

- [ ] Write implementation to make tests pass
- [ ] Run tests — they **pass** (green)
- [ ] Every new function has **type annotations** (params and return)
- [ ] Every new public function has a **docstring**
- [ ] New source files have the **BSD-2-Clause SPDX license header**

## Quality Gate (all must be green, zero exceptions)

```bash
# Run everything — this is what CI does
uv run ruff check .                                    # lint
uv run ruff format --check .                           # format
uv run mypy --strict python/pocket_dock/               # types
uv run bandit -r python/pocket_dock/ -c pyproject.toml # security
uv run pytest                                          # tests + coverage
```

- [ ] `ruff check` — zero warnings
- [ ] `ruff format` — zero diffs
- [ ] `mypy --strict` — zero errors
- [ ] `bandit` — zero findings
- [ ] `pytest` — all tests pass
- [ ] **100% line coverage** — no `# pragma: no cover`, no exclusions
- [ ] No new dependencies added to the SDK (stdlib only). CLI deps go in `[project.optional-dependencies.cli]`.

## Docs Sync (the step everyone skips — don't)

This is a **content review**, not a build step. `mkdocs build` renders markdown to HTML — it cannot tell you if the markdown is wrong. You have to read it.

- [ ] **README.md** — still matches current API and behavior?
- [ ] **Affected docs/ pages** — reflect this change? (concepts, guides, reference, config)
- [ ] **Python SDK examples** — affected ones still run? (`python examples/XX_name.py`)
- [ ] **CLI examples** — affected ones still run? (`bash examples/cli/XX_name.sh`)
- [ ] **CHANGELOG.md** — entry added under `[Unreleased]`
- [ ] **plan/spec.md** — updated if this was an architectural or API change
- [ ] **License headers** — all new `.py` files have the SPDX header

```bash
# Build docs to catch broken links / missing pages
uv run mkdocs build --strict
```

## Final Check

- [ ] Run full suite **again** after doc changes (they can break things)

```bash
uv run pre-commit run --all-files && uv run pytest
```

## Ship

- [ ] Push branch
- [ ] Open PR — title matches the change, description says what and why
- [ ] CI passes (lint + test matrix 3.10–3.13 + audit + docs build)
- [ ] Merge to `main`
- [ ] If this completes a milestone: tag release (`git tag -a v0.X.0 -m "M{N}: description"`)

---

## Quick Reference: Test Coverage Requirements

| Category | Requirement |
|---|---|
| Line coverage | 100% — every line reachable and tested |
| Golden path | Normal usage works end to end |
| Edge cases | Boundary values, empty/max input, type mismatches |
| Error paths | Timeouts, missing containers, bad state, invalid args |
| Cleanup | Resources freed on success, failure, crash, KeyboardInterrupt |
| Integration | Real Podman socket — no mocks |
| Concurrency | If feature involves async or multi-container, test concurrent use |

## Quick Reference: What Goes Where

| Changed | Update |
|---|---|
| Public SDK API | `docs/reference/api.md`, README if it's a core function |
| CLI command | `docs/reference/cli.md`, relevant `examples/cli/` script |
| Config field | `docs/reference/config.md`, `pocket-dock.yaml` example in spec |
| Error type | `docs/reference/errors.md` |
| New concept | Appropriate `docs/concepts/` page |
| Image profile | `docs/guides/` for the relevant workflow |
| Any of the above | `CHANGELOG.md` under `[Unreleased]` |