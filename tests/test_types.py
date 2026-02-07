"""Tests for pocket-dock data types."""

from __future__ import annotations

import dataclasses

import pocket_dock
import pytest
from pocket_dock.types import ExecResult


def test_exec_result_defaults() -> None:
    result = ExecResult(exit_code=0)
    assert result.exit_code == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.duration_ms == 0.0
    assert result.timed_out is False
    assert result.truncated is False


def test_exec_result_ok_true() -> None:
    result = ExecResult(exit_code=0, stdout="hello\n")
    assert result.ok is True


def test_exec_result_ok_false() -> None:
    result = ExecResult(exit_code=1, stderr="error\n")
    assert result.ok is False


def test_exec_result_ok_false_negative_exit() -> None:
    result = ExecResult(exit_code=-1, timed_out=True)
    assert result.ok is False


def test_exec_result_full_construction() -> None:
    result = ExecResult(
        exit_code=0,
        stdout="output",
        stderr="warnings",
        duration_ms=123.4,
        timed_out=False,
        truncated=True,
    )
    assert result.exit_code == 0
    assert result.stdout == "output"
    assert result.stderr == "warnings"
    assert result.duration_ms == 123.4
    assert result.timed_out is False
    assert result.truncated is True


def test_exec_result_is_frozen() -> None:
    result = ExecResult(exit_code=0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.exit_code = 1  # type: ignore[misc]


def test_exec_result_is_dataclass() -> None:
    assert dataclasses.is_dataclass(ExecResult)


def test_exec_result_exported_from_package() -> None:
    assert pocket_dock.ExecResult is ExecResult
