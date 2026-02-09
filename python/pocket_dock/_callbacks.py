# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Callback registry for container output events."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


class CallbackRegistry:
    """Registry for stdout/stderr/exit callbacks on a container.

    Errors in callbacks are suppressed to avoid breaking the frame read loop.
    """

    def __init__(self) -> None:
        self._stdout_cbs: list[Callable[..., object]] = []
        self._stderr_cbs: list[Callable[..., object]] = []
        self._exit_cbs: list[Callable[..., object]] = []

    def on_stdout(self, fn: Callable[..., object]) -> None:
        """Register a callback for stdout chunks: fn(container, data)."""
        self._stdout_cbs.append(fn)

    def on_stderr(self, fn: Callable[..., object]) -> None:
        """Register a callback for stderr chunks: fn(container, data)."""
        self._stderr_cbs.append(fn)

    def on_exit(self, fn: Callable[..., object]) -> None:
        """Register a callback for process exit: fn(container, exit_code)."""
        self._exit_cbs.append(fn)

    def dispatch_stdout(self, container: object, data: str) -> None:
        """Fire all stdout callbacks, suppressing errors."""
        for fn in self._stdout_cbs:
            with contextlib.suppress(Exception):
                fn(container, data)

    def dispatch_stderr(self, container: object, data: str) -> None:
        """Fire all stderr callbacks, suppressing errors."""
        for fn in self._stderr_cbs:
            with contextlib.suppress(Exception):
                fn(container, data)

    def dispatch_exit(self, container: object, exit_code: int) -> None:
        """Fire all exit callbacks, suppressing errors."""
        for fn in self._exit_cbs:
            with contextlib.suppress(Exception):
                fn(container, exit_code)
