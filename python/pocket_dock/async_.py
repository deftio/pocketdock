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

__all__ = [
    "AsyncContainer",
    "AsyncExecStream",
    "AsyncProcess",
    "AsyncSession",
    "create_new_container",
]
