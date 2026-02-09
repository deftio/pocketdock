# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import datetime


@dataclasses.dataclass(frozen=True)
class ContainerInfo:
    """Live snapshot of a container's state and resource usage."""

    id: str
    name: str
    status: str
    image: str
    created_at: datetime.datetime
    started_at: datetime.datetime | None = None
    uptime: datetime.timedelta | None = None
    memory_usage: str = ""
    memory_limit: str = ""
    memory_percent: float = 0.0
    cpu_percent: float = 0.0
    pids: int = 0
    network: bool = False
    ip_address: str = ""
    processes: tuple[dict[str, str], ...] = ()


@dataclasses.dataclass(frozen=True)
class ExecResult:
    """Result of executing a command inside a container."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    timed_out: bool = False
    truncated: bool = False

    @property
    def ok(self) -> bool:
        """Return True if the command exited successfully (exit code 0)."""
        return self.exit_code == 0
