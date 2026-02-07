"""Smoke test: verify the package is importable."""

from __future__ import annotations


def test_import_pocket_dock() -> None:
    import pocket_dock

    assert hasattr(pocket_dock, "__name__")
