# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Fire-and-forget logging to disk for container instances.

All I/O is synchronous filesystem writes — simple, no async overhead.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import datetime
    from pathlib import Path
    from typing import TextIO

    from pocketdock.types import ExecResult


class InstanceLogger:
    """Logs container commands and output to an instance's ``logs/`` directory."""

    def __init__(self, instance_dir: Path, *, enabled: bool = True) -> None:
        self._logs_dir = instance_dir / "logs"
        self._history_path = instance_dir / "logs" / "history.jsonl"
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        """Whether logging is active."""
        return self._enabled

    def log_run(self, command: str, result: ExecResult, started_at: datetime.datetime) -> None:
        """Write a log file for a completed ``run()`` call and append to history."""
        if not self._enabled:
            return

        ts = _safe_timestamp(started_at)
        log_name = f"run-{ts}.log"
        log_path = self._logs_dir / log_name

        lines = [
            f"# command: {command}",
            f"# exit_code: {result.exit_code}",
            f"# duration_ms: {result.duration_ms:.1f}",
            f"# timed_out: {result.timed_out}",
            "",
        ]
        if result.stdout:
            lines.append("--- stdout ---")
            lines.append(result.stdout)
        if result.stderr:
            lines.append("--- stderr ---")
            lines.append(result.stderr)

        log_path.write_text("\n".join(lines))

        self.append_history(
            {
                "type": "run",
                "command": command,
                "exit_code": result.exit_code,
                "duration_ms": round(result.duration_ms, 1),
                "timed_out": result.timed_out,
                "timestamp": started_at.isoformat(),
            }
        )

    def start_session_log(self, session_id: str) -> SessionLogHandle:
        """Create a session log file, return handle for incremental writes."""
        if not self._enabled:
            return SessionLogHandle(None)

        from datetime import datetime, timezone  # noqa: PLC0415

        ts = _safe_timestamp(datetime.now(tz=timezone.utc))
        log_path = self._logs_dir / f"session-{ts}.log"
        handle = log_path.open("a")
        handle.write(f"# session_id: {session_id}\n\n")
        return SessionLogHandle(handle)

    def start_detach_log(self, command: str) -> DetachLogHandle:
        """Create a detach log file, return handle for incremental writes."""
        if not self._enabled:
            return DetachLogHandle(None)

        from datetime import datetime, timezone  # noqa: PLC0415

        ts = _safe_timestamp(datetime.now(tz=timezone.utc))
        log_path = self._logs_dir / f"detach-{ts}.log"
        handle = log_path.open("a")
        handle.write(f"# command: {command}\n\n")
        return DetachLogHandle(handle)

    def append_history(self, entry: dict[str, object]) -> None:
        """Append one JSONL line to ``history.jsonl``."""
        if not self._enabled:
            return
        with self._history_path.open("a") as f:
            f.write(json.dumps(entry, default=str) + "\n")


class SessionLogHandle:
    """Handle for incremental writes to a session log file."""

    def __init__(self, handle: TextIO | None) -> None:
        self._handle = handle

    def write_send(self, command: str) -> None:
        """Log a command sent to the session."""
        if self._handle is None:
            return
        from datetime import datetime, timezone  # noqa: PLC0415

        ts = datetime.now(tz=timezone.utc).isoformat()
        self._handle.write(f"[{ts}] >>> {command}\n")
        self._handle.flush()

    def write_recv(self, data: str) -> None:
        """Log output received from the session."""
        if self._handle is None:
            return
        self._handle.write(data)
        self._handle.flush()

    def close(self) -> None:
        """Close the log file."""
        if self._handle is not None:
            self._handle.close()
            self._handle = None


class DetachLogHandle:
    """Handle for incremental writes to a detach log file."""

    def __init__(self, handle: TextIO | None) -> None:
        self._handle = handle

    def write_output(self, stream: str, data: str) -> None:
        """Log output from a detached process."""
        if self._handle is None:
            return
        from datetime import datetime, timezone  # noqa: PLC0415

        ts = datetime.now(tz=timezone.utc).isoformat()
        self._handle.write(f"[{ts}] [{stream}] {data}")
        self._handle.flush()

    def close(self, exit_code: int, duration_ms: float) -> None:
        """Close the log file with exit info."""
        if self._handle is not None:
            self._handle.write(f"\n# exit_code: {exit_code}\n# duration_ms: {duration_ms:.1f}\n")
            self._handle.close()
            self._handle = None


def _safe_timestamp(dt: datetime.datetime) -> str:
    """Format a datetime as a filesystem-safe ISO timestamp."""
    return dt.isoformat().replace(":", "-").replace("+", "p")
