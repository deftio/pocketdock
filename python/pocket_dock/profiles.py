# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Image profile registry and resolution.

Provides a mapping from profile names (``"minimal"``, ``"dev"``, etc.) to
image tags and metadata.  Used by :func:`create_new_container` to resolve
the ``profile`` parameter into an image name.
"""

from __future__ import annotations

import dataclasses
import pathlib


@dataclasses.dataclass(frozen=True)
class ProfileInfo:
    """Metadata for a built-in image profile."""

    name: str
    image_tag: str
    dockerfile_dir: str
    network_default: bool
    description: str
    size_estimate: str


PROFILES: dict[str, ProfileInfo] = {
    "minimal": ProfileInfo(
        name="minimal",
        image_tag="pocket-dock/minimal",
        dockerfile_dir="images/minimal",
        network_default=False,
        description="Lightest sandbox — Python 3, bash, busybox (~25 MB)",
        size_estimate="~25MB",
    ),
    "dev": ProfileInfo(
        name="dev",
        image_tag="pocket-dock/dev",
        dockerfile_dir="images/dev",
        network_default=True,
        description="Interactive dev sandbox — git, curl, vim, build tools, ipython (~250 MB)",
        size_estimate="~250MB",
    ),
    "agent": ProfileInfo(
        name="agent",
        image_tag="pocket-dock/agent",
        dockerfile_dir="images/agent",
        network_default=False,
        description="Agent sandbox — requests, pandas, numpy, beautifulsoup4 (~350 MB)",
        size_estimate="~350MB",
    ),
    "embedded": ProfileInfo(
        name="embedded",
        image_tag="pocket-dock/embedded",
        dockerfile_dir="images/embedded",
        network_default=True,
        description="C/C++ toolchain — GCC, CMake, ARM cross-compiler, Arduino CLI (~450 MB)",
        size_estimate="~450MB",
    ),
}


def resolve_profile(name: str) -> ProfileInfo:
    """Look up a profile by name.

    Args:
        name: One of ``"minimal"``, ``"dev"``, ``"agent"``, ``"embedded"``.

    Returns:
        The corresponding :class:`ProfileInfo`.

    Raises:
        ValueError: If *name* is not a known profile.

    """
    try:
        return PROFILES[name]
    except KeyError:
        known = ", ".join(sorted(PROFILES))
        msg = f"Unknown profile {name!r}. Known profiles: {known}"
        raise ValueError(msg) from None


def list_profiles() -> list[ProfileInfo]:
    """Return all built-in profiles."""
    return list(PROFILES.values())


def get_dockerfile_path(name: str) -> pathlib.Path:
    """Return the absolute path to a profile's Dockerfile directory.

    The path is resolved relative to the repository root, which is assumed
    to be three levels above this source file
    (``python/pocket_dock/profiles.py`` → repo root).

    Args:
        name: Profile name.

    Returns:
        Absolute :class:`~pathlib.Path` to the directory containing the
        Dockerfile.

    Raises:
        ValueError: If *name* is not a known profile.

    """
    info = resolve_profile(name)
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    return repo_root / info.dockerfile_dir
