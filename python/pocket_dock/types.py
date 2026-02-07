# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

from __future__ import annotations

import dataclasses


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
