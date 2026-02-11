"""Smoke test: verify the package is importable and versioned."""

from __future__ import annotations


def test_import_pocket_dock() -> None:
    import pocket_dock

    assert hasattr(pocket_dock, "__name__")


def test_version_attribute() -> None:
    import pocket_dock

    assert isinstance(pocket_dock.__version__, str)
    assert pocket_dock.__version__ == "0.9.0"


def test_get_version_function() -> None:
    from pocket_dock import get_version

    assert get_version() == "0.9.0"


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


def test_import_doctor() -> None:
    from pocket_dock import doctor

    assert callable(doctor)


def test_import_doctor_report() -> None:
    from pocket_dock import DoctorReport

    assert DoctorReport is not None


def test_import_project_not_initialized() -> None:
    from pocket_dock import ProjectNotInitialized

    assert issubclass(ProjectNotInitialized, Exception)


def test_import_find_project_root() -> None:
    from pocket_dock import find_project_root

    assert callable(find_project_root)


def test_import_init_project() -> None:
    from pocket_dock import init_project

    assert callable(init_project)


def test_import_async_doctor() -> None:
    from pocket_dock.async_ import doctor

    assert callable(doctor)


def test_import_async_find_project_root() -> None:
    from pocket_dock.async_ import find_project_root

    assert callable(find_project_root)


def test_import_async_init_project() -> None:
    from pocket_dock.async_ import init_project

    assert callable(init_project)


def test_import_stop_container() -> None:
    from pocket_dock import stop_container

    assert callable(stop_container)


def test_import_async_stop_container() -> None:
    from pocket_dock.async_ import stop_container

    assert callable(stop_container)


def test_import_cli_main() -> None:
    from pocket_dock.cli.main import cli

    assert callable(cli)
