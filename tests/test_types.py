"""Tests for pocketdock data types."""

from __future__ import annotations

import dataclasses
import datetime

import pocketdock
import pytest
from pocketdock.types import ContainerInfo, ExecResult, StreamChunk


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
    assert pocketdock.ExecResult is ExecResult


# --- ContainerInfo ---


def test_container_info_defaults() -> None:
    info = ContainerInfo(
        id="abc123",
        name="pd-test",
        status="running",
        image="test-image",
        created_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
    )
    assert info.id == "abc123"
    assert info.name == "pd-test"
    assert info.status == "running"
    assert info.image == "test-image"
    assert info.started_at is None
    assert info.uptime is None
    assert info.memory_usage == ""
    assert info.memory_limit == ""
    assert info.memory_percent == 0.0
    assert info.cpu_percent == 0.0
    assert info.pids == 0
    assert info.network is False
    assert info.ip_address == ""
    assert info.processes == ()


def test_container_info_full_construction() -> None:
    created = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    started = datetime.datetime(2026, 1, 1, 0, 1, tzinfo=datetime.timezone.utc)
    info = ContainerInfo(
        id="abc123",
        name="pd-full",
        status="running",
        image="test-image",
        created_at=created,
        started_at=started,
        uptime=datetime.timedelta(seconds=60),
        memory_usage="42.1 MB",
        memory_limit="256.0 MB",
        memory_percent=16.45,
        cpu_percent=5.2,
        pids=3,
        network=True,
        ip_address="172.17.0.2",
        processes=({"PID": "1", "CMD": "sleep"},),
    )
    assert info.started_at == started
    assert info.uptime == datetime.timedelta(seconds=60)
    assert info.memory_usage == "42.1 MB"
    assert info.memory_percent == 16.45
    assert info.pids == 3
    assert info.network is True
    assert info.ip_address == "172.17.0.2"
    assert len(info.processes) == 1


def test_container_info_ports_default() -> None:
    info = ContainerInfo(
        id="abc",
        name="pd-test",
        status="running",
        image="test",
        created_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
    )
    assert info.ports == {}


def test_container_info_ports_set() -> None:
    info = ContainerInfo(
        id="abc",
        name="pd-test",
        status="running",
        image="test",
        created_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        ports={8080: 80, 3000: 3000},
    )
    assert info.ports == {8080: 80, 3000: 3000}


def test_container_info_is_frozen() -> None:
    info = ContainerInfo(
        id="x",
        name="n",
        status="s",
        image="i",
        created_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        info.status = "changed"  # type: ignore[misc]


def test_container_info_is_dataclass() -> None:
    assert dataclasses.is_dataclass(ContainerInfo)


def test_container_info_exported_from_package() -> None:
    assert pocketdock.ContainerInfo is ContainerInfo


# --- StreamChunk ---


def test_stream_chunk_construction() -> None:
    chunk = StreamChunk(stream="stdout", data="hello")
    assert chunk.stream == "stdout"
    assert chunk.data == "hello"


def test_stream_chunk_is_frozen() -> None:
    chunk = StreamChunk(stream="stderr", data="err")
    with pytest.raises(dataclasses.FrozenInstanceError):
        chunk.data = "x"  # type: ignore[misc]


def test_stream_chunk_is_dataclass() -> None:
    assert dataclasses.is_dataclass(StreamChunk)


def test_stream_chunk_exported_from_package() -> None:
    assert pocketdock.StreamChunk is StreamChunk
