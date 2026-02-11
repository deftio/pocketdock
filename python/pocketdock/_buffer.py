# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Thread-safe ring buffer for detached process output accumulation."""

from __future__ import annotations

import dataclasses
import threading

from pocketdock._stream import STREAM_STDOUT


@dataclasses.dataclass(frozen=True)
class BufferSnapshot:
    """Snapshot of buffered output."""

    stdout: str
    stderr: str


class RingBuffer:
    """Bounded ring buffer for stdout/stderr accumulation.

    Each stream (stdout, stderr) gets half the total capacity.
    When a stream's buffer exceeds its half, the oldest bytes are evicted.
    Thread-safe via threading.Lock.
    """

    def __init__(self, capacity: int = 1_048_576) -> None:
        self._half = max(capacity // 2, 1)
        self._lock = threading.Lock()
        self._stdout = bytearray()
        self._stderr = bytearray()
        self._overflow = False

    def write(self, stream_type: int, data: bytes) -> None:
        """Append data to the appropriate stream buffer, evicting if needed."""
        with self._lock:
            buf = self._stdout if stream_type == STREAM_STDOUT else self._stderr
            buf.extend(data)
            if len(buf) > self._half:
                excess = len(buf) - self._half
                del buf[:excess]
                self._overflow = True

    def read(self) -> BufferSnapshot:
        """Drain and return all buffered output."""
        with self._lock:
            snapshot = BufferSnapshot(
                stdout=bytes(self._stdout).decode("utf-8", errors="replace"),
                stderr=bytes(self._stderr).decode("utf-8", errors="replace"),
            )
            self._stdout.clear()
            self._stderr.clear()
            return snapshot

    def peek(self) -> BufferSnapshot:
        """Return buffered output without draining."""
        with self._lock:
            return BufferSnapshot(
                stdout=bytes(self._stdout).decode("utf-8", errors="replace"),
                stderr=bytes(self._stderr).decode("utf-8", errors="replace"),
            )

    @property
    def size(self) -> int:
        """Current bytes in buffer (stdout + stderr)."""
        with self._lock:
            return len(self._stdout) + len(self._stderr)

    @property
    def overflow(self) -> bool:
        """True if any data was evicted due to capacity."""
        with self._lock:
            return self._overflow
