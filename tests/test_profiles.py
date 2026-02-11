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


def test_resolve_minimal() -> None:
    info = resolve_profile("minimal")
    assert info.name == "minimal"
    assert info.image_tag == "pocketdock/minimal"


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
    with pytest.raises(ValueError, match=r"agent.*dev.*embedded.*minimal"):
        resolve_profile("bad")


# --- list_profiles ---


def test_list_profiles_returns_all() -> None:
    profiles = list_profiles()
    assert len(profiles) == 4


def test_list_profiles_types() -> None:
    for p in list_profiles():
        assert isinstance(p, ProfileInfo)


def test_list_profiles_names() -> None:
    names = {p.name for p in list_profiles()}
    assert names == {"minimal", "dev", "agent", "embedded"}


# --- get_dockerfile_path ---


def test_get_dockerfile_path_minimal() -> None:
    path = get_dockerfile_path("minimal")
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


def test_profiles_dict_has_four_entries() -> None:
    assert len(PROFILES) == 4


def test_profile_info_frozen() -> None:
    info = resolve_profile("minimal")
    with pytest.raises(AttributeError):
        info.name = "other"  # type: ignore[misc]


# --- ProfileInfo fields ---


def test_profile_info_fields() -> None:
    info = resolve_profile("dev")
    assert info.dockerfile_dir == "images/dev"
    assert info.description
    assert info.size_estimate
