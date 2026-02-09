"""Tests for RingBuffer and BufferSnapshot."""

from __future__ import annotations

import dataclasses
import threading

from pocket_dock._buffer import BufferSnapshot, RingBuffer
from pocket_dock._stream import STREAM_STDERR, STREAM_STDOUT


# --- BufferSnapshot ---


def test_buffer_snapshot_defaults() -> None:
    snap = BufferSnapshot(stdout="", stderr="")
    assert snap.stdout == ""
    assert snap.stderr == ""


def test_buffer_snapshot_is_frozen() -> None:
    import pytest

    snap = BufferSnapshot(stdout="a", stderr="b")
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.stdout = "x"  # type: ignore[misc]


def test_buffer_snapshot_is_dataclass() -> None:
    assert dataclasses.is_dataclass(BufferSnapshot)


# --- RingBuffer basics ---


def test_ring_buffer_empty() -> None:
    buf = RingBuffer()
    snap = buf.read()
    assert snap.stdout == ""
    assert snap.stderr == ""
    assert buf.size == 0
    assert buf.overflow is False


def test_ring_buffer_write_stdout() -> None:
    buf = RingBuffer()
    buf.write(STREAM_STDOUT, b"hello")
    assert buf.size == 5
    snap = buf.peek()
    assert snap.stdout == "hello"
    assert snap.stderr == ""


def test_ring_buffer_write_stderr() -> None:
    buf = RingBuffer()
    buf.write(STREAM_STDERR, b"error")
    assert buf.size == 5
    snap = buf.peek()
    assert snap.stdout == ""
    assert snap.stderr == "error"


def test_ring_buffer_write_both_streams() -> None:
    buf = RingBuffer()
    buf.write(STREAM_STDOUT, b"out")
    buf.write(STREAM_STDERR, b"err")
    assert buf.size == 6
    snap = buf.peek()
    assert snap.stdout == "out"
    assert snap.stderr == "err"


# --- read vs peek ---


def test_ring_buffer_read_drains() -> None:
    buf = RingBuffer()
    buf.write(STREAM_STDOUT, b"data")
    snap1 = buf.read()
    assert snap1.stdout == "data"
    snap2 = buf.read()
    assert snap2.stdout == ""
    assert buf.size == 0


def test_ring_buffer_peek_does_not_drain() -> None:
    buf = RingBuffer()
    buf.write(STREAM_STDOUT, b"data")
    snap1 = buf.peek()
    assert snap1.stdout == "data"
    snap2 = buf.peek()
    assert snap2.stdout == "data"
    assert buf.size == 4


# --- overflow ---


def test_ring_buffer_overflow_stdout() -> None:
    buf = RingBuffer(capacity=20)  # 10 per stream
    buf.write(STREAM_STDOUT, b"x" * 15)
    assert buf.overflow is True
    snap = buf.peek()
    assert len(snap.stdout) == 10
    assert snap.stdout == "x" * 10


def test_ring_buffer_overflow_stderr() -> None:
    buf = RingBuffer(capacity=20)
    buf.write(STREAM_STDERR, b"y" * 15)
    assert buf.overflow is True
    snap = buf.peek()
    assert len(snap.stderr) == 10


def test_ring_buffer_no_overflow_within_limit() -> None:
    buf = RingBuffer(capacity=20)
    buf.write(STREAM_STDOUT, b"x" * 10)
    assert buf.overflow is False
    assert buf.size == 10


def test_ring_buffer_evicts_oldest() -> None:
    buf = RingBuffer(capacity=20)  # 10 per stream
    buf.write(STREAM_STDOUT, b"ABCDE")
    buf.write(STREAM_STDOUT, b"12345678")  # total=13, exceeds 10
    snap = buf.peek()
    # oldest 3 bytes evicted: "ABC" gone, "DE12345678" → last 10
    assert snap.stdout == "DE12345678"


def test_ring_buffer_multiple_writes_overflow() -> None:
    buf = RingBuffer(capacity=10)  # 5 per stream
    buf.write(STREAM_STDOUT, b"abc")
    buf.write(STREAM_STDOUT, b"defgh")  # total=8, cap=5 → evict 3
    assert buf.overflow is True
    snap = buf.peek()
    assert snap.stdout == "defgh"


# --- capacity edge cases ---


def test_ring_buffer_minimum_capacity() -> None:
    buf = RingBuffer(capacity=1)  # half = max(0, 1) = 1
    buf.write(STREAM_STDOUT, b"AB")
    assert buf.overflow is True
    snap = buf.peek()
    assert snap.stdout == "B"


def test_ring_buffer_utf8_decode() -> None:
    buf = RingBuffer()
    buf.write(STREAM_STDOUT, "héllo".encode())
    snap = buf.read()
    assert snap.stdout == "héllo"


def test_ring_buffer_invalid_utf8_replace() -> None:
    buf = RingBuffer()
    buf.write(STREAM_STDOUT, b"\xff\xfe")
    snap = buf.read()
    assert "\ufffd" in snap.stdout  # replacement character


# --- thread safety ---


def test_ring_buffer_concurrent_writes() -> None:
    buf = RingBuffer(capacity=1_048_576)
    errors: list[Exception] = []

    def writer(stream: int, data: bytes, count: int) -> None:
        try:
            for _ in range(count):
                buf.write(stream, data)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    t1 = threading.Thread(target=writer, args=(STREAM_STDOUT, b"a", 1000))
    t2 = threading.Thread(target=writer, args=(STREAM_STDERR, b"b", 1000))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
    snap = buf.read()
    assert len(snap.stdout) == 1000
    assert len(snap.stderr) == 1000
