# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Project management — .pocket-dock/ directory, instance dirs, metadata."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

from pocket_dock.types import DoctorReport

_CONFIG_FILENAME = "pocket-dock.yaml"
_INSTANCES_DIR = "instances"

_DEFAULT_YAML_TEMPLATE = """\
# Project configuration for pocket-dock
project_name: {project_name}
default_profile: minimal
default_persist: false

logging:
  auto_log: true
  max_log_size: "10MB"
  max_logs_per_instance: 100
  retention_days: 30
"""


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk up from *start* (default: cwd) looking for ``.pocket-dock/pocket-dock.yaml``.

    Returns the directory containing ``.pocket-dock/``, or ``None`` if not found.
    """
    current = (start or Path.cwd()).resolve()
    while True:
        candidate = current / ".pocket-dock" / _CONFIG_FILENAME
        if candidate.is_file():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def init_project(path: Path | None = None, *, project_name: str | None = None) -> Path:
    """Create ``.pocket-dock/pocket-dock.yaml`` in *path* (default: cwd).

    Returns the project root path (the directory containing ``.pocket-dock/``).
    """
    root = (path or Path.cwd()).resolve()
    pd_dir = root / ".pocket-dock"
    pd_dir.mkdir(parents=True, exist_ok=True)

    name = project_name or root.name
    config_path = pd_dir / _CONFIG_FILENAME
    if not config_path.exists():
        config_path.write_text(_DEFAULT_YAML_TEMPLATE.format(project_name=name))

    # Ensure instances dir exists
    (pd_dir / _INSTANCES_DIR).mkdir(exist_ok=True)

    return root


def get_project_name(project_root: Path) -> str:
    """Parse ``pocket-dock.yaml`` for ``project_name``, fallback to dir name."""
    config_path = project_root / ".pocket-dock" / _CONFIG_FILENAME
    if config_path.is_file():
        try:
            data = yaml.safe_load(config_path.read_text())
            if isinstance(data, dict):
                name = data.get("project_name")
                if isinstance(name, str) and name:
                    return name
        except yaml.YAMLError:
            pass
    return project_root.name


def ensure_instance_dir(project_root: Path, instance_name: str) -> Path:
    """Create ``.pocket-dock/instances/{name}/`` with ``logs/`` and ``data/`` subdirs.

    Returns the instance directory path.
    """
    instance_dir = project_root / ".pocket-dock" / _INSTANCES_DIR / instance_name
    instance_dir.mkdir(parents=True, exist_ok=True)
    (instance_dir / "logs").mkdir(exist_ok=True)
    (instance_dir / "data").mkdir(exist_ok=True)
    return instance_dir


def write_instance_metadata(  # noqa: PLR0913
    instance_dir: Path,
    *,
    container_id: str = "",
    name: str = "",
    image: str = "",
    project: str = "",
    created_at: str = "",
    persist: bool = False,
    mem_limit: str = "",
    cpu_percent: int = 0,
) -> None:
    """Write ``instance.toml`` with container metadata and provenance.

    Uses a simple TOML emitter (flat sections, trivial to generate).
    """
    lines = ["# Maintained by pocket-dock. Do not edit.", ""]

    # --- container section ---
    container_pairs: list[tuple[str, object]] = []
    if container_id:
        container_pairs.append(("id", container_id))
    if name:
        container_pairs.append(("name", name))
    if image:
        container_pairs.append(("image", image))
    if project:
        container_pairs.append(("project", project))
    if created_at:
        container_pairs.append(("created_at", created_at))
    container_pairs.append(("persist", persist))

    if container_pairs:
        _emit_section(lines, "container", container_pairs)

    # --- resources section ---
    resource_pairs: list[tuple[str, object]] = []
    if mem_limit:
        resource_pairs.append(("mem_limit", mem_limit))
    if cpu_percent:
        resource_pairs.append(("cpu_percent", cpu_percent))

    if resource_pairs:
        _emit_section(lines, "resources", resource_pairs)

    # --- provenance section ---
    provenance_pairs: list[tuple[str, object]] = [
        ("created_by", " ".join(sys.argv)),
        ("pid", os.getpid()),
    ]
    _emit_section(lines, "provenance", provenance_pairs)

    (instance_dir / "instance.toml").write_text("\n".join(lines))


def read_instance_metadata(instance_dir: Path) -> dict[str, Any]:
    """Read ``instance.toml`` via ``tomllib``/``tomli``. Return parsed dict."""
    toml_path = instance_dir / "instance.toml"
    if not toml_path.is_file():
        return {}

    try:
        import tomllib  # type: ignore[import-not-found]  # noqa: PLC0415
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]  # noqa: PLC0415

    return tomllib.loads(toml_path.read_text())


def remove_instance_dir(project_root: Path, instance_name: str) -> bool:
    """Remove the instance directory. Returns ``True`` if removed."""
    instance_dir = project_root / ".pocket-dock" / _INSTANCES_DIR / instance_name
    if instance_dir.is_dir():
        shutil.rmtree(instance_dir)
        return True
    return False


def list_instance_dirs(project_root: Path) -> list[Path]:
    """List all directories under ``.pocket-dock/instances/``."""
    instances_dir = project_root / ".pocket-dock" / _INSTANCES_DIR
    if not instances_dir.is_dir():
        return []
    return sorted(p for p in instances_dir.iterdir() if p.is_dir())


async def doctor(
    *,
    project_root: Path | None = None,
    socket_path: str | None = None,
) -> DoctorReport:
    """Cross-reference local instance dirs with engine containers.

    Args:
        project_root: Explicit project root. Auto-detected if ``None``.
        socket_path: Path to the engine socket. Auto-detected if ``None``.

    Returns:
        A :class:`DoctorReport` with orphaned containers, stale dirs, and healthy count.

    Raises:
        ProjectNotInitialized: If no ``.pocket-dock/`` project directory is found.

    """
    from pocket_dock.errors import ProjectNotInitialized  # noqa: PLC0415
    from pocket_dock.persistence import list_containers  # noqa: PLC0415

    if project_root is None:
        project_root = find_project_root()
    if project_root is None:
        raise ProjectNotInitialized

    config_file = project_root / ".pocket-dock" / _CONFIG_FILENAME
    if not config_file.is_file():
        raise ProjectNotInitialized

    project_name = get_project_name(project_root)

    # Local instance directory names
    local_dirs = {p.name for p in list_instance_dirs(project_root)}

    # Engine containers for this project
    items = await list_containers(socket_path=socket_path, project=project_name)
    container_names = {item.name for item in items}

    orphaned = tuple(sorted(container_names - local_dirs))
    stale = tuple(sorted(local_dirs - container_names))
    healthy = len(local_dirs & container_names)

    return DoctorReport(
        orphaned_containers=orphaned,
        stale_instance_dirs=stale,
        healthy=healthy,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _emit_section(lines: list[str], name: str, pairs: list[tuple[str, object]]) -> None:
    """Append a TOML section to *lines*."""
    lines.append(f"[{name}]")
    for k, v in pairs:
        lines.append(f"{k} = {_toml_value(v)}")
    lines.append("")


def _toml_value(v: object) -> str:
    """Format a Python value as a TOML literal."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return f'"{v}"'
    return f'"{v}"'
