"""Unit tests for _config.py — configuration loading with precedence."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from pocketdock._config import PocketDockConfig, _build_config, _merge_yaml, load_config

if TYPE_CHECKING:
    from pathlib import Path

# --- Default config ---


def test_default_config_values() -> None:
    cfg = PocketDockConfig()
    assert cfg.project_name == ""
    assert cfg.default_profile == "minimal"
    assert cfg.default_persist is False
    assert cfg.auto_log is True
    assert cfg.max_log_size == "10MB"
    assert cfg.max_logs_per_instance == 100
    assert cfg.retention_days == 30
    assert cfg.socket is None
    assert cfg.log_level == "info"


def test_config_is_frozen() -> None:
    import pytest

    cfg = PocketDockConfig()
    with pytest.raises(AttributeError):
        cfg.project_name = "changed"  # type: ignore[misc]


# --- load_config ---


def test_load_config_no_files_returns_defaults() -> None:
    cfg = load_config(project_root=None)
    assert cfg == PocketDockConfig()


def test_load_config_project_override(tmp_path: Path) -> None:
    pd_dir = tmp_path / ".pocketdock"
    pd_dir.mkdir()
    (pd_dir / "pocketdock.yaml").write_text(
        "project_name: my-app\ndefault_profile: dev\ndefault_persist: true\n"
    )

    cfg = load_config(project_root=tmp_path)
    assert cfg.project_name == "my-app"
    assert cfg.default_profile == "dev"
    assert cfg.default_persist is True
    # Other defaults unchanged
    assert cfg.auto_log is True


def test_load_config_install_level_override(tmp_path: Path) -> None:
    install_dir = tmp_path / ".pocketdock"
    install_dir.mkdir()
    (install_dir / "pocketdock.yaml").write_text("socket: /custom/sock\nlog_level: debug\n")

    with patch("pocketdock._config.Path.home", return_value=tmp_path):
        cfg = load_config(project_root=None)

    assert cfg.socket == "/custom/sock"
    assert cfg.log_level == "debug"


def test_load_config_project_overrides_install(tmp_path: Path) -> None:
    # Install-level
    install_dir = tmp_path / "home" / ".pocketdock"
    install_dir.mkdir(parents=True)
    (install_dir / "pocketdock.yaml").write_text("default_profile: dev\nlog_level: debug\n")

    # Project-level overrides profile but not log_level
    project_root = tmp_path / "project"
    project_root.mkdir()
    pd_dir = project_root / ".pocketdock"
    pd_dir.mkdir()
    (pd_dir / "pocketdock.yaml").write_text("default_profile: agent\n")

    with patch("pocketdock._config.Path.home", return_value=tmp_path / "home"):
        cfg = load_config(project_root=project_root)

    assert cfg.default_profile == "agent"  # project wins
    assert cfg.log_level == "debug"  # install-level inherited


def test_load_config_logging_section(tmp_path: Path) -> None:
    pd_dir = tmp_path / ".pocketdock"
    pd_dir.mkdir()
    (pd_dir / "pocketdock.yaml").write_text(
        "logging:\n  auto_log: false\n  max_log_size: 50MB\n  retention_days: 7\n"
    )

    cfg = load_config(project_root=tmp_path)
    assert cfg.auto_log is False
    assert cfg.max_log_size == "50MB"
    assert cfg.retention_days == 7


def test_load_config_missing_project_dir(tmp_path: Path) -> None:
    cfg = load_config(project_root=tmp_path)
    assert cfg == PocketDockConfig()


# --- _merge_yaml ---


def test_merge_yaml_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(": invalid: yaml: {[")

    target: dict[str, object] = {}
    _merge_yaml(target, path)
    assert target == {}


def test_merge_yaml_non_dict(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text("- item1\n- item2\n")

    target: dict[str, object] = {}
    _merge_yaml(target, path)
    assert target == {}


def test_merge_yaml_flattens_logging(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("logging:\n  auto_log: false\n  max_log_size: 20MB\n")

    target: dict[str, object] = {}
    _merge_yaml(target, path)
    assert target["auto_log"] is False
    assert target["max_log_size"] == "20MB"


# --- _build_config ---


def test_build_config_filters_unknown_keys() -> None:
    cfg = _build_config({"project_name": "test", "unknown_key": "ignored"})
    assert cfg.project_name == "test"


def test_build_config_empty() -> None:
    cfg = _build_config({})
    assert cfg == PocketDockConfig()
