"""Unit tests for the profiles module."""

from __future__ import annotations

import pytest
from pocketdock.profiles import (
    PROFILES,
    ProfileInfo,
    get_dockerfile_path,
    list_profiles,
    resolve_profile,
)

# --- resolve_profile ---


def test_resolve_minimal_python() -> None:
    info = resolve_profile("minimal-python")
    assert info.name == "minimal-python"
    assert info.image_tag == "pocketdock/minimal-python"


def test_resolve_minimal_node() -> None:
    info = resolve_profile("minimal-node")
    assert info.name == "minimal-node"
    assert info.image_tag == "pocketdock/minimal-node"
    assert info.network_default is False


def test_resolve_minimal_bun() -> None:
    info = resolve_profile("minimal-bun")
    assert info.name == "minimal-bun"
    assert info.image_tag == "pocketdock/minimal-bun"
    assert info.network_default is False


def test_resolve_dev() -> None:
    info = resolve_profile("dev")
    assert info.name == "dev"
    assert info.image_tag == "pocketdock/dev"
    assert info.network_default is True


def test_resolve_agent() -> None:
    info = resolve_profile("agent")
    assert info.name == "agent"
    assert info.image_tag == "pocketdock/agent"
    assert info.network_default is False


def test_resolve_embedded() -> None:
    info = resolve_profile("embedded")
    assert info.name == "embedded"
    assert info.image_tag == "pocketdock/embedded"
    assert info.network_default is True


def test_resolve_unknown_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown profile 'nope'"):
        resolve_profile("nope")


def test_resolve_unknown_lists_known_profiles() -> None:
    with pytest.raises(
        ValueError, match=r"agent.*dev.*embedded.*minimal-bun.*minimal-node.*minimal-python"
    ):
        resolve_profile("bad")


# --- list_profiles ---


def test_list_profiles_returns_all() -> None:
    profiles = list_profiles()
    assert len(profiles) == 6


def test_list_profiles_types() -> None:
    for p in list_profiles():
        assert isinstance(p, ProfileInfo)


def test_list_profiles_names() -> None:
    names = {p.name for p in list_profiles()}
    assert names == {"minimal-python", "minimal-node", "minimal-bun", "dev", "agent", "embedded"}


# --- get_dockerfile_path ---


def test_get_dockerfile_path_minimal_python() -> None:
    path = get_dockerfile_path("minimal-python")
    assert path.is_dir()
    assert (path / "Dockerfile").is_file()


def test_get_dockerfile_path_minimal_node() -> None:
    path = get_dockerfile_path("minimal-node")
    assert path.is_dir()
    assert (path / "Dockerfile").is_file()


def test_get_dockerfile_path_minimal_bun() -> None:
    path = get_dockerfile_path("minimal-bun")
    assert path.is_dir()
    assert (path / "Dockerfile").is_file()


def test_get_dockerfile_path_dev() -> None:
    path = get_dockerfile_path("dev")
    assert path.is_dir()
    assert (path / "Dockerfile").is_file()


def test_get_dockerfile_path_agent() -> None:
    path = get_dockerfile_path("agent")
    assert path.is_dir()
    assert (path / "Dockerfile").is_file()


def test_get_dockerfile_path_embedded() -> None:
    path = get_dockerfile_path("embedded")
    assert path.is_dir()
    assert (path / "Dockerfile").is_file()


def test_get_dockerfile_path_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown profile"):
        get_dockerfile_path("nonexistent")


# --- PROFILES dict ---


def test_profiles_dict_has_six_entries() -> None:
    assert len(PROFILES) == 6


def test_profile_info_frozen() -> None:
    info = resolve_profile("minimal-python")
    with pytest.raises(AttributeError):
        info.name = "other"  # type: ignore[misc]


# --- ProfileInfo fields ---


def test_minimal_python_demo_files_bundled() -> None:
    path = get_dockerfile_path("minimal-python")
    assert (path / "demo" / "index.html").is_file()
    assert (path / "demo" / "serve.py").is_file()
    assert (path / "demo" / "README.md").is_file()


def test_profile_info_fields() -> None:
    info = resolve_profile("dev")
    assert info.dockerfile_dir == "_images/dev"
    assert info.description
    assert info.size_estimate
