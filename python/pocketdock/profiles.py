# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Image profile registry and resolution.

Provides a mapping from profile names (``"minimal-python"``, ``"dev"``, etc.)
to image tags and metadata.  Used by :func:`create_new_container` to resolve
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
    "minimal-python": ProfileInfo(
        name="minimal-python",
        image_tag="pocketdock/minimal-python",
        dockerfile_dir="_images/minimal-python",
        network_default=False,
        description="Lightest sandbox — Python 3, bash, busybox (~25 MB)",
        size_estimate="~25MB",
    ),
    "minimal-node": ProfileInfo(
        name="minimal-node",
        image_tag="pocketdock/minimal-node",
        dockerfile_dir="_images/minimal-node",
        network_default=False,
        description="Node.js sandbox — Node 22, npm, bash (~60 MB)",
        size_estimate="~60MB",
    ),
    "minimal-bun": ProfileInfo(
        name="minimal-bun",
        image_tag="pocketdock/minimal-bun",
        dockerfile_dir="_images/minimal-bun",
        network_default=False,
        description="Bun sandbox — Bun runtime, bash (~100 MB)",
        size_estimate="~100MB",
    ),
    "dev": ProfileInfo(
        name="dev",
        image_tag="pocketdock/dev",
        dockerfile_dir="_images/dev",
        network_default=True,
        description="Interactive dev sandbox — git, curl, vim, build tools, ipython (~250 MB)",
        size_estimate="~250MB",
    ),
    "agent": ProfileInfo(
        name="agent",
        image_tag="pocketdock/agent",
        dockerfile_dir="_images/agent",
        network_default=False,
        description="Agent sandbox — requests, pandas, numpy, beautifulsoup4 (~350 MB)",
        size_estimate="~350MB",
    ),
    "embedded": ProfileInfo(
        name="embedded",
        image_tag="pocketdock/embedded",
        dockerfile_dir="_images/embedded",
        network_default=True,
        description="C/C++ toolchain — GCC, CMake, ARM cross-compiler, Arduino CLI (~450 MB)",
        size_estimate="~450MB",
    ),
}


def resolve_profile(name: str) -> ProfileInfo:
    """Look up a profile by name.

    Args:
        name: One of ``"minimal-python"``, ``"minimal-node"``, ``"minimal-bun"``,
              ``"dev"``, ``"agent"``, ``"embedded"``.

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

    The Dockerfiles are bundled inside the package at
    ``pocketdock/_images/<profile>/``.

    Args:
        name: Profile name.

    Returns:
        Absolute :class:`~pathlib.Path` to the directory containing the
        Dockerfile.

    Raises:
        ValueError: If *name* is not a known profile.

    """
    info = resolve_profile(name)
    # _images/ lives next to this file inside the installed package.
    package_dir = pathlib.Path(__file__).resolve().parent
    return package_dir / info.dockerfile_dir
