"""Unit tests for stream demux protocol parsing."""

from __future__ import annotations

import asyncio
import struct

from pocket_dock._stream import (
    HEADER_SIZE,
    STREAM_STDERR,
    STREAM_STDOUT,
    DemuxResult,
    demux_stream,
    parse_stream_header,
)


def _make_frame(stream_type: int, data: bytes) -> bytes:
    """Build a Docker stream multiplexed frame."""
    header = struct.pack(">BxxxI", stream_type, len(data))
    return header + data


def test_parse_stream_header_stdout() -> None:
    header = struct.pack(">BxxxI", STREAM_STDOUT, 42)
    stream_type, length = parse_stream_header(header)
    assert stream_type == STREAM_STDOUT
    assert length == 42


def test_parse_stream_header_stderr() -> None:
    header = struct.pack(">BxxxI", STREAM_STDERR, 100)
    stream_type, length = parse_stream_header(header)
    assert stream_type == STREAM_STDERR
    assert length == 100


def test_header_size_is_eight() -> None:
    assert HEADER_SIZE == 8


def test_demux_result_stdout_text() -> None:
    result = DemuxResult(stdout_bytes=b"hello\n", stderr_bytes=b"")
    assert result.stdout_text() == "hello\n"


def test_demux_result_stderr_text() -> None:
    result = DemuxResult(stdout_bytes=b"", stderr_bytes=b"error\n")
    assert result.stderr_text() == "error\n"


def test_demux_result_defaults() -> None:
    result = DemuxResult()
    assert result.stdout_bytes == b""
    assert result.stderr_bytes == b""
    assert result.truncated is False


async def test_demux_stream_stdout_only() -> None:
    data = _make_frame(STREAM_STDOUT, b"hello world\n")
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()

    result = await demux_stream(reader)
    assert result.stdout_text() == "hello world\n"
    assert result.stderr_text() == ""
    assert result.truncated is False


async def test_demux_stream_stderr_only() -> None:
    data = _make_frame(STREAM_STDERR, b"error message\n")
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()

    result = await demux_stream(reader)
    assert result.stdout_text() == ""
    assert result.stderr_text() == "error message\n"


async def test_demux_stream_mixed() -> None:
    data = (
        _make_frame(STREAM_STDOUT, b"out\n")
        + _make_frame(STREAM_STDERR, b"err\n")
        + _make_frame(STREAM_STDOUT, b"more out\n")
    )
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()

    result = await demux_stream(reader)
    assert result.stdout_text() == "out\nmore out\n"
    assert result.stderr_text() == "err\n"


async def test_demux_stream_empty() -> None:
    reader = asyncio.StreamReader()
    reader.feed_eof()

    result = await demux_stream(reader)
    assert result.stdout_text() == ""
    assert result.stderr_text() == ""
    assert result.truncated is False


async def test_demux_stream_truncation() -> None:
    # Create data larger than max_output
    big_payload = b"x" * 1000
    data = _make_frame(STREAM_STDOUT, big_payload)
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()

    result = await demux_stream(reader, max_output=100)
    assert len(result.stdout_bytes) <= 100
    assert result.truncated is True


async def test_demux_stream_truncation_at_boundary() -> None:
    # First frame fills up to max, second frame triggers truncation
    data = (
        _make_frame(STREAM_STDOUT, b"x" * 50)
        + _make_frame(STREAM_STDOUT, b"y" * 50)
        + _make_frame(STREAM_STDOUT, b"z" * 50)
    )
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()

    result = await demux_stream(reader, max_output=100)
    assert len(result.stdout_bytes) == 100
    assert result.truncated is True


async def test_demux_stream_zero_length_frame() -> None:
    # Zero-length payload frame should be skipped
    zero_frame = struct.pack(">BxxxI", STREAM_STDOUT, 0)
    data = zero_frame + _make_frame(STREAM_STDOUT, b"after zero\n")
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()

    result = await demux_stream(reader)
    assert result.stdout_text() == "after zero\n"


async def test_demux_stream_partial_header_eof() -> None:
    # EOF in the middle of a header
    reader = asyncio.StreamReader()
    reader.feed_data(b"\x01\x00\x00")  # partial header
    reader.feed_eof()

    result = await demux_stream(reader)
    assert result.stdout_text() == ""
    assert result.stderr_text() == ""


async def test_demux_stream_partial_payload_eof() -> None:
    # Header says 100 bytes, but only 10 arrive before EOF
    header = struct.pack(">BxxxI", STREAM_STDOUT, 100)
    reader = asyncio.StreamReader()
    reader.feed_data(header + b"short")
    reader.feed_eof()

    result = await demux_stream(reader)
    # partial payload is lost because _read_exact returns b"" on partial read
    assert result.stdout_text() == ""


async def test_demux_result_utf8_replacement() -> None:
    # Invalid UTF-8 bytes should be replaced, not crash
    result = DemuxResult(stdout_bytes=b"\xff\xfe", stderr_bytes=b"\x80\x81")
    assert isinstance(result.stdout_text(), str)
    assert isinstance(result.stderr_text(), str)


async def test_demux_stream_max_output_zero_remaining() -> None:
    # Already at max_output when next frame arrives
    data = _make_frame(STREAM_STDOUT, b"x" * 100) + _make_frame(STREAM_STDOUT, b"overflow")
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()

    result = await demux_stream(reader, max_output=100)
    assert len(result.stdout_bytes) == 100
    assert result.truncated is True


async def test_demux_stream_unknown_stream_type() -> None:
    # Stream type 0 (stdin) is neither stdout(1) nor stderr(2) — silently ignored
    data = _make_frame(0, b"stdin data") + _make_frame(STREAM_STDOUT, b"out\n")
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()

    result = await demux_stream(reader)
    assert result.stdout_text() == "out\n"
    assert result.stderr_text() == ""
