# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Async public API for pocketdock.

Usage::

    from pocketdock.async_ import create_new_container

    async def main():
        async with await create_new_container() as c:
            result = await c.run("echo hello")
            print(result.stdout)
"""

from __future__ import annotations

from pocketdock._async_container import AsyncContainer, create_new_container
from pocketdock._process import AsyncExecStream, AsyncProcess
from pocketdock._session import AsyncSession
from pocketdock.persistence import (
    destroy_container,
    list_containers,
    prune,
    resume_container,
    stop_container,
)
from pocketdock.profiles import ProfileInfo, list_profiles, resolve_profile
from pocketdock.projects import doctor, find_project_root, init_project

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
