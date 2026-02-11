# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Async public API for pocket-dock.

Usage::

    from pocket_dock.async_ import create_new_container

    async def main():
        async with await create_new_container() as c:
            result = await c.run("echo hello")
            print(result.stdout)
"""

from __future__ import annotations

from pocket_dock._async_container import AsyncContainer, create_new_container
from pocket_dock._process import AsyncExecStream, AsyncProcess
from pocket_dock._session import AsyncSession
from pocket_dock.persistence import (
    destroy_container,
    list_containers,
    prune,
    resume_container,
    stop_container,
)
from pocket_dock.profiles import ProfileInfo, list_profiles, resolve_profile
from pocket_dock.projects import doctor, find_project_root, init_project

__all__ = [
    "AsyncContainer",
    "AsyncExecStream",
    "AsyncProcess",
    "AsyncSession",
    "ProfileInfo",
    "create_new_container",
    "destroy_container",
    "doctor",
    "find_project_root",
    "init_project",
    "list_containers",
    "list_profiles",
    "prune",
    "resolve_profile",
    "resume_container",
    "stop_container",
]
