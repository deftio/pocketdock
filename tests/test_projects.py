"""Unit tests for projects.py — .pocketdock/ directory management.

All tests use tmp_path for filesystem isolation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml
from pocketdock.projects import (
    _toml_value,
    ensure_instance_dir,
    find_project_root,
    get_project_name,
    init_project,
    list_instance_dirs,
    read_instance_metadata,
    remove_instance_dir,
    write_instance_metadata,
)

if TYPE_CHECKING:
    from pathlib import Path

# --- find_project_root ---


def test_find_project_root_from_project_dir(tmp_path: Path) -> None:
    pd_dir = tmp_path / ".pocketdock"
    pd_dir.mkdir()
    (pd_dir / "pocketdock.yaml").write_text("project_name: test")

    assert find_project_root(tmp_path) == tmp_path


def test_find_project_root_from_subdirectory(tmp_path: Path) -> None:
    pd_dir = tmp_path / ".pocketdock"
    pd_dir.mkdir()
    (pd_dir / "pocketdock.yaml").write_text("project_name: test")

    sub = tmp_path / "a" / "b" / "c"
    sub.mkdir(parents=True)

    assert find_project_root(sub) == tmp_path


def test_find_project_root_returns_none_when_missing(tmp_path: Path) -> None:
    assert find_project_root(tmp_path) is None


def test_find_project_root_requires_yaml_file(tmp_path: Path) -> None:
    # .pocketdock dir exists but no pocketdock.yaml
    (tmp_path / ".pocketdock").mkdir()
    assert find_project_root(tmp_path) is None


def test_find_project_root_default_start(tmp_path: Path) -> None:
    import os

    pd_dir = tmp_path / ".pocketdock"
    pd_dir.mkdir()
    (pd_dir / "pocketdock.yaml").write_text("project_name: test")

    os.chdir(tmp_path)
    assert find_project_root() == tmp_path


# --- init_project ---


def test_init_project_creates_structure(tmp_path: Path) -> None:
    root = init_project(tmp_path, project_name="my-widget")

    assert root == tmp_path
    assert (tmp_path / ".pocketdock" / "pocketdock.yaml").is_file()
    assert (tmp_path / ".pocketdock" / "instances").is_dir()


def test_init_project_yaml_content(tmp_path: Path) -> None:
    init_project(tmp_path, project_name="my-widget")

    content = (tmp_path / ".pocketdock" / "pocketdock.yaml").read_text()
    data = yaml.safe_load(content)
    assert data["project_name"] == "my-widget"
    assert data["default_profile"] == "minimal"
    assert data["default_persist"] is False
    assert data["logging"]["auto_log"] is True


def test_init_project_default_name_uses_dirname(tmp_path: Path) -> None:
    init_project(tmp_path)

    content = (tmp_path / ".pocketdock" / "pocketdock.yaml").read_text()
    data = yaml.safe_load(content)
    assert data["project_name"] == tmp_path.name


def test_init_project_idempotent(tmp_path: Path) -> None:
    init_project(tmp_path, project_name="first")

    # Modify the file
    config = tmp_path / ".pocketdock" / "pocketdock.yaml"
    original = config.read_text()

    # Re-init should NOT overwrite existing config
    init_project(tmp_path, project_name="second")
    assert config.read_text() == original


def test_init_project_default_cwd(tmp_path: Path) -> None:
    import os

    os.chdir(tmp_path)
    root = init_project()
    assert root == tmp_path


# --- get_project_name ---


def test_get_project_name_from_yaml(tmp_path: Path) -> None:
    init_project(tmp_path, project_name="cool-project")
    assert get_project_name(tmp_path) == "cool-project"


def test_get_project_name_falls_back_to_dirname(tmp_path: Path) -> None:
    # No .pocketdock dir at all
    assert get_project_name(tmp_path) == tmp_path.name


def test_get_project_name_empty_yaml(tmp_path: Path) -> None:
    pd_dir = tmp_path / ".pocketdock"
    pd_dir.mkdir()
    (pd_dir / "pocketdock.yaml").write_text("")
    assert get_project_name(tmp_path) == tmp_path.name


def test_get_project_name_invalid_yaml(tmp_path: Path) -> None:
    pd_dir = tmp_path / ".pocketdock"
    pd_dir.mkdir()
    (pd_dir / "pocketdock.yaml").write_text(": invalid: yaml: {[")
    assert get_project_name(tmp_path) == tmp_path.name


def test_get_project_name_empty_string_in_yaml(tmp_path: Path) -> None:
    pd_dir = tmp_path / ".pocketdock"
    pd_dir.mkdir()
    (pd_dir / "pocketdock.yaml").write_text('project_name: ""')
    assert get_project_name(tmp_path) == tmp_path.name


def test_get_project_name_non_string_in_yaml(tmp_path: Path) -> None:
    pd_dir = tmp_path / ".pocketdock"
    pd_dir.mkdir()
    (pd_dir / "pocketdock.yaml").write_text("project_name: 42")
    assert get_project_name(tmp_path) == tmp_path.name


# --- ensure_instance_dir ---


def test_ensure_instance_dir_creates_structure(tmp_path: Path) -> None:
    init_project(tmp_path)
    instance_dir = ensure_instance_dir(tmp_path, "pd-abc12345")

    assert instance_dir.is_dir()
    assert (instance_dir / "logs").is_dir()
    assert (instance_dir / "data").is_dir()


def test_ensure_instance_dir_idempotent(tmp_path: Path) -> None:
    init_project(tmp_path)
    d1 = ensure_instance_dir(tmp_path, "pd-abc12345")
    d2 = ensure_instance_dir(tmp_path, "pd-abc12345")
    assert d1 == d2


# --- write_instance_metadata / read_instance_metadata ---


def test_write_and_read_instance_metadata(tmp_path: Path) -> None:
    init_project(tmp_path)
    instance_dir = ensure_instance_dir(tmp_path, "pd-test1234")

    write_instance_metadata(
        instance_dir,
        container_id="a1b2c3d4",
        name="pd-test1234",
        image="pocketdock/minimal",
        project="my-widget",
        created_at="2026-02-05T09:15:00Z",
        persist=True,
        mem_limit="256m",
        cpu_percent=50,
    )

    metadata = read_instance_metadata(instance_dir)
    assert metadata["container"]["id"] == "a1b2c3d4"
    assert metadata["container"]["name"] == "pd-test1234"
    assert metadata["container"]["image"] == "pocketdock/minimal"
    assert metadata["container"]["persist"] is True
    assert metadata["resources"]["mem_limit"] == "256m"
    assert metadata["resources"]["cpu_percent"] == 50
    assert "created_by" in metadata["provenance"]
    assert isinstance(metadata["provenance"]["pid"], int)


def test_read_instance_metadata_missing_file(tmp_path: Path) -> None:
    assert read_instance_metadata(tmp_path) == {}


def test_write_instance_metadata_minimal(tmp_path: Path) -> None:
    init_project(tmp_path)
    instance_dir = ensure_instance_dir(tmp_path, "pd-min")

    write_instance_metadata(instance_dir, container_id="abc", name="pd-min")
    metadata = read_instance_metadata(instance_dir)
    assert metadata["container"]["id"] == "abc"
    assert "resources" not in metadata
    assert "provenance" in metadata


# --- remove_instance_dir ---


def test_remove_instance_dir_success(tmp_path: Path) -> None:
    init_project(tmp_path)
    ensure_instance_dir(tmp_path, "pd-toremove")
    assert remove_instance_dir(tmp_path, "pd-toremove") is True
    assert not (tmp_path / ".pocketdock" / "instances" / "pd-toremove").exists()


def test_remove_instance_dir_nonexistent(tmp_path: Path) -> None:
    init_project(tmp_path)
    assert remove_instance_dir(tmp_path, "pd-ghost") is False


# --- list_instance_dirs ---


def test_list_instance_dirs_empty(tmp_path: Path) -> None:
    init_project(tmp_path)
    assert list_instance_dirs(tmp_path) == []


def test_list_instance_dirs_multiple(tmp_path: Path) -> None:
    init_project(tmp_path)
    ensure_instance_dir(tmp_path, "pd-aaa")
    ensure_instance_dir(tmp_path, "pd-bbb")
    ensure_instance_dir(tmp_path, "pd-ccc")

    dirs = list_instance_dirs(tmp_path)
    names = [d.name for d in dirs]
    assert names == ["pd-aaa", "pd-bbb", "pd-ccc"]


def test_list_instance_dirs_no_instances_dir(tmp_path: Path) -> None:
    # No .pocketdock/instances/ dir
    assert list_instance_dirs(tmp_path) == []


# --- _toml_value ---


def test_toml_value_bool() -> None:
    val_true: object = True
    val_false: object = False
    assert _toml_value(val_true) == "true"
    assert _toml_value(val_false) == "false"


def test_toml_value_int() -> None:
    assert _toml_value(42) == "42"


def test_toml_value_str() -> None:
    assert _toml_value("hello") == '"hello"'


def test_write_instance_metadata_all_defaults(tmp_path: Path) -> None:
    init_project(tmp_path)
    instance_dir = ensure_instance_dir(tmp_path, "pd-defaults")

    write_instance_metadata(instance_dir)
    metadata = read_instance_metadata(instance_dir)
    # Container section has at least "persist"
    assert metadata["container"]["persist"] is False
    assert "resources" not in metadata


def test_toml_value_other() -> None:
    assert _toml_value(3.14) == '"3.14"'


# --- tomli fallback coverage ---


def test_write_instance_metadata_with_ports(tmp_path: Path) -> None:
    init_project(tmp_path)
    instance_dir = ensure_instance_dir(tmp_path, "pd-porttest")

    write_instance_metadata(
        instance_dir,
        container_id="abc",
        name="pd-porttest",
        ports={8080: 80, 3000: 3000},
    )
    metadata = read_instance_metadata(instance_dir)
    assert "ports" in metadata
    # TOML keys are strings, values are ints
    assert metadata["ports"]["8080"] == 80
    assert metadata["ports"]["3000"] == 3000


def test_write_instance_metadata_no_ports(tmp_path: Path) -> None:
    init_project(tmp_path)
    instance_dir = ensure_instance_dir(tmp_path, "pd-noport")

    write_instance_metadata(instance_dir, container_id="abc", name="pd-noport")
    metadata = read_instance_metadata(instance_dir)
    assert "ports" not in metadata


def test_read_instance_metadata_tomli_fallback(tmp_path: Path) -> None:
    """Ensure the tomli fallback import path is covered."""
    import builtins
    import sys

    init_project(tmp_path)
    instance_dir = ensure_instance_dir(tmp_path, "pd-fallback")
    write_instance_metadata(instance_dir, container_id="abc", name="pd-fallback")

    # Remove cached tomllib from sys.modules and block re-import
    saved = sys.modules.pop("tomllib", None)
    real_import = builtins.__import__

    def _block_tomllib(name: str, *args: object, **kwargs: object) -> object:
        if name == "tomllib":
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    builtins.__import__ = _block_tomllib  # type: ignore[assignment]
    try:
        metadata = read_instance_metadata(instance_dir)
        assert metadata["container"]["id"] == "abc"
    finally:
        builtins.__import__ = real_import  # type: ignore[assignment]
        if saved is not None:
            sys.modules["tomllib"] = saved
