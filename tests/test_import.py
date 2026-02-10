"""Smoke test: verify the package is importable and versioned."""

from __future__ import annotations


def test_import_pocket_dock() -> None:
    import pocket_dock

    assert hasattr(pocket_dock, "__name__")


def test_version_attribute() -> None:
    import pocket_dock

    assert isinstance(pocket_dock.__version__, str)
    assert pocket_dock.__version__ == "0.7.0"


def test_get_version_function() -> None:
    from pocket_dock import get_version

    assert get_version() == "0.7.0"


def test_import_resume_container() -> None:
    from pocket_dock import resume_container

    assert callable(resume_container)


def test_import_list_containers() -> None:
    from pocket_dock import list_containers

    assert callable(list_containers)


def test_import_destroy_container() -> None:
    from pocket_dock import destroy_container

    assert callable(destroy_container)


def test_import_prune() -> None:
    from pocket_dock import prune

    assert callable(prune)


def test_import_container_list_item() -> None:
    from pocket_dock import ContainerListItem

    assert ContainerListItem is not None


def test_import_async_persistence() -> None:
    from pocket_dock.async_ import (
        destroy_container,
        list_containers,
        prune,
        resume_container,
    )

    assert callable(resume_container)
    assert callable(list_containers)
    assert callable(destroy_container)
    assert callable(prune)
