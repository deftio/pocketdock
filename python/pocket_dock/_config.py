# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Configuration loading with install-level -> project-level precedence."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import yaml

_CONFIG_FILENAME = "pocket-dock.yaml"


@dataclasses.dataclass(frozen=True)
class PocketDockConfig:
    """Resolved pocket-dock configuration."""

    project_name: str = ""
    default_profile: str = "minimal"
    default_persist: bool = False
    auto_log: bool = True
    max_log_size: str = "10MB"
    max_logs_per_instance: int = 100
    retention_days: int = 30
    socket: str | None = None
    log_level: str = "info"


def load_config(project_root: Path | None = None) -> PocketDockConfig:
    """Load configuration with precedence: project > install > defaults.

    1. Start with defaults
    2. Overlay install-level ``~/.pocket-dock/pocket-dock.yaml`` (if exists)
    3. Overlay project-level ``.pocket-dock/pocket-dock.yaml`` (if exists)
    """
    overrides: dict[str, Any] = {}

    # Install-level config
    install_config = Path.home() / ".pocket-dock" / _CONFIG_FILENAME
    if install_config.is_file():
        _merge_yaml(overrides, install_config)

    # Project-level config
    if project_root is not None:
        project_config = project_root / ".pocket-dock" / _CONFIG_FILENAME
        if project_config.is_file():
            _merge_yaml(overrides, project_config)

    return _build_config(overrides)


def _merge_yaml(target: dict[str, Any], path: Path) -> None:
    """Parse a YAML file and merge its values into *target*."""
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError:
        return
    if not isinstance(data, dict):
        return

    for key, value in data.items():
        if key == "logging" and isinstance(value, dict):
            # Flatten logging sub-keys into top-level config keys
            target.update(value)
        else:
            target[key] = value


def _build_config(overrides: dict[str, Any]) -> PocketDockConfig:
    """Build a ``PocketDockConfig`` from a dict of overrides."""
    field_names = {f.name for f in dataclasses.fields(PocketDockConfig)}
    filtered = {k: v for k, v in overrides.items() if k in field_names}
    return PocketDockConfig(**filtered)
