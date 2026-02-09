"""Smoke test: verify the package is importable and versioned."""

from __future__ import annotations


def test_import_pocket_dock() -> None:
    import pocket_dock

    assert hasattr(pocket_dock, "__name__")


def test_version_attribute() -> None:
    import pocket_dock

    assert isinstance(pocket_dock.__version__, str)
    assert pocket_dock.__version__ == "0.4.0"


def test_get_version_function() -> None:
    from pocket_dock import get_version

    assert get_version() == "0.4.0"
