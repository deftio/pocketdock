"""Unit tests for socket client pure functions and HTTP parsing.

These tests don't require a running container engine. They test the parsing
logic directly using in-memory asyncio.StreamReader instances.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    import pathlib

import pytest
from pocket_dock._socket_client import (
    _check_container_response,
    _read_body,
    _read_chunked,
    _read_exact_body,
    _read_headers,
    _read_status_line,
    _send_request,
    detect_socket,
)
from pocket_dock.errors import (
    ContainerNotFound,
    ContainerNotRunning,
    SocketCommunicationError,
)

# -- detect_socket --


def test_detect_socket_with_env_var(tmp_path: pathlib.Path) -> None:
    sock = tmp_path / "test.sock"
    sock.touch()
    with patch.dict(os.environ, {"POCKET_DOCK_SOCKET": str(sock)}):
        assert detect_socket() == str(sock)


def test_detect_socket_env_var_nonexistent() -> None:
    with patch.dict(os.environ, {"POCKET_DOCK_SOCKET": "/tmp/nonexistent.sock"}):
        # Falls through to candidate list; may or may not find Docker
        result = detect_socket()
        # Just verify it doesn't return the nonexistent path
        assert result != "/tmp/nonexistent.sock"


def test_detect_socket_no_env_no_candidates() -> None:
    with (
        patch.dict(os.environ, {"POCKET_DOCK_SOCKET": "", "XDG_RUNTIME_DIR": "/tmp/fake_xdg"}),
        patch("pocket_dock._socket_client.pathlib.Path.exists", return_value=False),
    ):
        assert detect_socket() is None


# -- _read_status_line --


async def test_read_status_line_200() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"HTTP/1.1 200 OK\r\n")
    reader.feed_eof()
    assert await _read_status_line(reader) == 200


async def test_read_status_line_404() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"HTTP/1.1 404 Not Found\r\n")
    reader.feed_eof()
    assert await _read_status_line(reader) == 404


async def test_read_status_line_empty() -> None:
    reader = asyncio.StreamReader()
    reader.feed_eof()
    with pytest.raises(SocketCommunicationError, match="empty response"):
        await _read_status_line(reader)


async def test_read_status_line_malformed() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"GARBAGE\r\n")
    reader.feed_eof()
    with pytest.raises(SocketCommunicationError, match="malformed"):
        await _read_status_line(reader)


# -- _read_headers --


async def test_read_headers_simple() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"Content-Type: application/json\r\nContent-Length: 42\r\n\r\n")
    reader.feed_eof()
    headers = await _read_headers(reader)
    assert headers["content-type"] == "application/json"
    assert headers["content-length"] == "42"


async def test_read_headers_empty() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"\r\n")
    reader.feed_eof()
    headers = await _read_headers(reader)
    assert headers == {}


# -- _read_body --


async def test_read_body_content_length() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"hello world")
    reader.feed_eof()
    body = await _read_body(reader, {"content-length": "11"})
    assert body == b"hello world"


async def test_read_body_chunked() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n")
    reader.feed_eof()
    body = await _read_body(reader, {"transfer-encoding": "chunked"})
    assert body == b"hello world"


async def test_read_body_until_eof() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"some data until eof")
    reader.feed_eof()
    body = await _read_body(reader, {})
    assert body == b"some data until eof"


# -- _read_exact_body --


async def test_read_exact_body_full() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"1234567890")
    reader.feed_eof()
    body = await _read_exact_body(reader, 10)
    assert body == b"1234567890"


async def test_read_exact_body_short() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"short")
    reader.feed_eof()
    body = await _read_exact_body(reader, 100)
    assert body == b"short"


# -- _read_chunked --


async def test_read_chunked_multiple_chunks() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"3\r\nabc\r\n4\r\ndefg\r\n0\r\n\r\n")
    reader.feed_eof()
    body = await _read_chunked(reader)
    assert body == b"abcdefg"


async def test_read_chunked_single_chunk() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"a\r\n0123456789\r\n0\r\n\r\n")
    reader.feed_eof()
    body = await _read_chunked(reader)
    assert body == b"0123456789"


# -- _send_request --


async def test_send_request_with_body() -> None:
    transport = _MockTransport()
    loop = asyncio.get_running_loop()
    protocol = asyncio.StreamReaderProtocol(asyncio.StreamReader())
    writer = asyncio.StreamWriter(transport, protocol, reader=asyncio.StreamReader(), loop=loop)

    await _send_request(writer, "POST", "/test", b'{"key":"value"}')

    written = transport.data
    assert b"POST /test HTTP/1.1\r\n" in written
    assert b"Host: localhost\r\n" in written
    assert b"Content-Type: application/json\r\n" in written
    assert b"Content-Length: 15\r\n" in written
    assert b'{"key":"value"}' in written


async def test_send_request_without_body() -> None:
    transport = _MockTransport()
    loop = asyncio.get_running_loop()
    protocol = asyncio.StreamReaderProtocol(asyncio.StreamReader())
    writer = asyncio.StreamWriter(transport, protocol, reader=asyncio.StreamReader(), loop=loop)

    await _send_request(writer, "GET", "/_ping")

    written = transport.data
    assert b"GET /_ping HTTP/1.1\r\n" in written
    assert b"Host: localhost\r\n" in written
    assert b"Content-Type" not in written
    assert b"Content-Length" not in written


# -- _check_container_response --


def test_check_response_success() -> None:
    # Should not raise for success status codes
    _check_container_response(200, b"ok", "test-id")
    _check_container_response(204, b"", "test-id")
    _check_container_response(304, b"", "test-id")


def test_check_response_404() -> None:
    with pytest.raises(ContainerNotFound):
        _check_container_response(404, b"not found", "test-id")


def test_check_response_409() -> None:
    with pytest.raises(ContainerNotRunning):
        _check_container_response(409, b"conflict", "test-id")


def test_check_response_500() -> None:
    with pytest.raises(SocketCommunicationError, match="HTTP 500"):
        _check_container_response(500, b"internal error", "test-id")


# -- Helpers --


class _MockTransport(asyncio.Transport):
    """Minimal transport that captures written bytes."""

    def __init__(self) -> None:
        super().__init__()
        self.data = b""
        self._closing = False

    def write(self, data: bytes) -> None:  # type: ignore[override]
        self.data += data

    def close(self) -> None:
        self._closing = True

    def is_closing(self) -> bool:
        return self._closing

    def get_extra_info(  # type: ignore[override]
        self, _name: str, default: object = None
    ) -> object:
        return default
