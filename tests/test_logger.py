"""Unit tests for _logger.py — auto-logging and command history."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pocket_dock._logger import (
    DetachLogHandle,
    InstanceLogger,
    SessionLogHandle,
    _safe_timestamp,
)
from pocket_dock.projects import ensure_instance_dir, init_project
from pocket_dock.types import ExecResult

if TYPE_CHECKING:
    from pathlib import Path

# --- _safe_timestamp ---


def test_safe_timestamp() -> None:
    dt = datetime(2026, 2, 10, 14, 30, 0, tzinfo=timezone.utc)
    ts = _safe_timestamp(dt)
    assert ":" not in ts
    assert "+" not in ts
    assert "2026-02-10T14-30-00" in ts


# --- InstanceLogger ---


def _make_logger(tmp_path: Path) -> tuple[InstanceLogger, Path]:
    init_project(tmp_path)
    instance_dir = ensure_instance_dir(tmp_path, "pd-test1234")
    logger = InstanceLogger(instance_dir)
    return logger, instance_dir


def test_logger_enabled_by_default(tmp_path: Path) -> None:
    logger, _ = _make_logger(tmp_path)
    assert logger.enabled is True


def test_logger_disabled(tmp_path: Path) -> None:
    init_project(tmp_path)
    instance_dir = ensure_instance_dir(tmp_path, "pd-disabled")
    logger = InstanceLogger(instance_dir, enabled=False)
    assert logger.enabled is False


# --- log_run ---


def test_log_run_creates_log_file(tmp_path: Path) -> None:
    logger, instance_dir = _make_logger(tmp_path)
    started = datetime(2026, 2, 10, 14, 30, 0, tzinfo=timezone.utc)
    result = ExecResult(exit_code=0, stdout="hello\n", stderr="", duration_ms=47.5)

    logger.log_run("echo hello", result, started)

    logs_dir = instance_dir / "logs"
    log_files = list(logs_dir.glob("run-*.log"))
    assert len(log_files) == 1

    content = log_files[0].read_text()
    assert "command: echo hello" in content
    assert "exit_code: 0" in content
    assert "duration_ms: 47.5" in content
    assert "hello\n" in content


def test_log_run_with_stderr(tmp_path: Path) -> None:
    logger, instance_dir = _make_logger(tmp_path)
    started = datetime(2026, 2, 10, 14, 30, 0, tzinfo=timezone.utc)
    result = ExecResult(exit_code=1, stdout="", stderr="error\n", duration_ms=10.0)

    logger.log_run("bad-cmd", result, started)

    log_files = list((instance_dir / "logs").glob("run-*.log"))
    content = log_files[0].read_text()
    assert "--- stderr ---" in content
    assert "error\n" in content


def test_log_run_appends_to_history(tmp_path: Path) -> None:
    logger, instance_dir = _make_logger(tmp_path)
    started = datetime(2026, 2, 10, 14, 30, 0, tzinfo=timezone.utc)
    result = ExecResult(exit_code=0, stdout="ok\n", duration_ms=5.0)

    logger.log_run("echo ok", result, started)

    history = instance_dir / "logs" / "history.jsonl"
    assert history.exists()
    line = json.loads(history.read_text().strip())
    assert line["type"] == "run"
    assert line["command"] == "echo ok"
    assert line["exit_code"] == 0
    assert line["duration_ms"] == 5.0


def test_log_run_disabled_is_noop(tmp_path: Path) -> None:
    init_project(tmp_path)
    instance_dir = ensure_instance_dir(tmp_path, "pd-noop")
    logger = InstanceLogger(instance_dir, enabled=False)
    started = datetime(2026, 2, 10, 14, 30, 0, tzinfo=timezone.utc)
    result = ExecResult(exit_code=0, stdout="ok\n", duration_ms=5.0)

    logger.log_run("echo ok", result, started)

    log_files = list((instance_dir / "logs").glob("run-*.log"))
    assert len(log_files) == 0


def test_log_run_timed_out(tmp_path: Path) -> None:
    logger, instance_dir = _make_logger(tmp_path)
    started = datetime(2026, 2, 10, 14, 30, 0, tzinfo=timezone.utc)
    result = ExecResult(exit_code=-1, stdout="", duration_ms=30000.0, timed_out=True)

    logger.log_run("sleep 60", result, started)

    log_files = list((instance_dir / "logs").glob("run-*.log"))
    content = log_files[0].read_text()
    assert "timed_out: True" in content


# --- Session log ---


def test_session_log_write_and_close(tmp_path: Path) -> None:
    logger, instance_dir = _make_logger(tmp_path)

    handle = logger.start_session_log("exec-123")
    handle.write_send("ls -la")
    handle.write_recv("total 0\n")
    handle.close()

    log_files = list((instance_dir / "logs").glob("session-*.log"))
    assert len(log_files) == 1

    content = log_files[0].read_text()
    assert "session_id: exec-123" in content
    assert ">>> ls -la" in content
    assert "total 0\n" in content


def test_session_log_disabled(tmp_path: Path) -> None:
    init_project(tmp_path)
    instance_dir = ensure_instance_dir(tmp_path, "pd-nosess")
    logger = InstanceLogger(instance_dir, enabled=False)

    handle = logger.start_session_log("exec-123")
    handle.write_send("ls")
    handle.write_recv("data")
    handle.close()

    log_files = list((instance_dir / "logs").glob("session-*.log"))
    assert len(log_files) == 0


# --- Detach log ---


def test_detach_log_write_and_close(tmp_path: Path) -> None:
    logger, instance_dir = _make_logger(tmp_path)

    handle = logger.start_detach_log("sleep 10")
    handle.write_output("stdout", "hello\n")
    handle.write_output("stderr", "warning\n")
    handle.close(exit_code=0, duration_ms=100.5)

    log_files = list((instance_dir / "logs").glob("detach-*.log"))
    assert len(log_files) == 1

    content = log_files[0].read_text()
    assert "command: sleep 10" in content
    assert "[stdout] hello\n" in content
    assert "[stderr] warning\n" in content
    assert "exit_code: 0" in content
    assert "duration_ms: 100.5" in content


def test_detach_log_disabled(tmp_path: Path) -> None:
    init_project(tmp_path)
    instance_dir = ensure_instance_dir(tmp_path, "pd-nodet")
    logger = InstanceLogger(instance_dir, enabled=False)

    handle = logger.start_detach_log("cmd")
    handle.write_output("stdout", "data")
    handle.close(exit_code=0, duration_ms=0.0)

    log_files = list((instance_dir / "logs").glob("detach-*.log"))
    assert len(log_files) == 0


# --- append_history ---


def test_append_history_multiple_entries(tmp_path: Path) -> None:
    logger, instance_dir = _make_logger(tmp_path)

    logger.append_history({"type": "run", "command": "cmd1"})
    logger.append_history({"type": "run", "command": "cmd2"})

    history = instance_dir / "logs" / "history.jsonl"
    lines = history.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["command"] == "cmd1"
    assert json.loads(lines[1])["command"] == "cmd2"


def test_append_history_disabled(tmp_path: Path) -> None:
    init_project(tmp_path)
    instance_dir = ensure_instance_dir(tmp_path, "pd-nohist")
    logger = InstanceLogger(instance_dir, enabled=False)

    logger.append_history({"type": "test"})

    history = instance_dir / "logs" / "history.jsonl"
    assert not history.exists()


# --- Handle edge cases ---


def test_session_log_handle_close_idempotent() -> None:
    handle = SessionLogHandle(None)
    handle.close()  # should not raise
    handle.close()  # idempotent


def test_detach_log_handle_close_idempotent() -> None:
    handle = DetachLogHandle(None)
    handle.close(exit_code=0, duration_ms=0.0)  # should not raise
    handle.close(exit_code=0, duration_ms=0.0)  # idempotent
