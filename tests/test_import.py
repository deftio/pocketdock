"""Smoke test: verify the package is importable and versioned."""

from __future__ import annotations


def test_import_pocketdock() -> None:
    import pocketdock

    assert hasattr(pocketdock, "__name__")


def test_version_attribute() -> None:
    import pocketdock

    assert isinstance(pocketdock.__version__, str)
    assert pocketdock.__version__ == "1.2.4"


def test_get_version_function() -> None:
    from pocketdock import get_version

    assert get_version() == "1.2.4"


def test_import_resume_container() -> None:
    from pocketdock import resume_container

    assert callable(resume_container)


def test_import_list_containers() -> None:
    from pocketdock import list_containers

    assert callable(list_containers)


def test_import_destroy_container() -> None:
    from pocketdock import destroy_container

    assert callable(destroy_container)


def test_import_prune() -> None:
    from pocketdock import prune

    assert callable(prune)


def test_import_container_list_item() -> None:
    from pocketdock import ContainerListItem

    assert ContainerListItem is not None


def test_import_async_persistence() -> None:
    from pocketdock.async_ import (
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
    from pocketdock import doctor

    assert callable(doctor)


def test_import_doctor_report() -> None:
    from pocketdock import DoctorReport

    assert DoctorReport is not None


def test_import_project_not_initialized() -> None:
    from pocketdock import ProjectNotInitialized

    assert issubclass(ProjectNotInitialized, Exception)


def test_import_find_project_root() -> None:
    from pocketdock import find_project_root

    assert callable(find_project_root)


def test_import_init_project() -> None:
    from pocketdock import init_project

    assert callable(init_project)


def test_import_async_doctor() -> None:
    from pocketdock.async_ import doctor

    assert callable(doctor)


def test_import_async_find_project_root() -> None:
    from pocketdock.async_ import find_project_root

    assert callable(find_project_root)


def test_import_async_init_project() -> None:
    from pocketdock.async_ import init_project

    assert callable(init_project)


def test_import_stop_container() -> None:
    from pocketdock import stop_container

    assert callable(stop_container)


def test_import_async_stop_container() -> None:
    from pocketdock.async_ import stop_container

    assert callable(stop_container)


def test_import_cli_main() -> None:
    from pocketdock.cli.main import cli

    assert callable(cli)


def test_import_profile_info() -> None:
    from pocketdock import ProfileInfo

    assert ProfileInfo is not None


def test_import_resolve_profile() -> None:
    from pocketdock import resolve_profile

    assert callable(resolve_profile)


def test_import_list_profiles() -> None:
    from pocketdock import list_profiles

    assert callable(list_profiles)


def test_import_async_resolve_profile() -> None:
    from pocketdock.async_ import resolve_profile

    assert callable(resolve_profile)


def test_import_async_list_profiles() -> None:
    from pocketdock.async_ import list_profiles

    assert callable(list_profiles)
