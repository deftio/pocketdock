"""Unit tests for socket client pure functions and HTTP parsing.

These tests don't require a running container engine. They test the parsing
logic directly using in-memory asyncio.StreamReader instances.
"""

from __future__ import annotations

import asyncio
import os
import struct
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

if TYPE_CHECKING:
    import pathlib

import pytest
from pocket_dock._socket_client import (
    _check_container_response,
    _exec_create,
    _exec_inspect_exit_code,
    _exec_start,
    _read_body,
    _read_chunked,
    _read_exact_body,
    _read_headers,
    _read_status_line,
    _request,
    _request_raw,
    _request_stream,
    _send_request,
    create_container,
    detect_socket,
    ping,
    pull_archive,
    push_archive,
    remove_container,
    start_container,
    stop_container,
)
from pocket_dock.errors import (
    ContainerNotFound,
    ContainerNotRunning,
    ImageNotFound,
    SocketCommunicationError,
    SocketConnectionError,
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


def _make_mock_writer() -> MagicMock:
    """Create a mock writer with close() and wait_closed()."""
    writer = MagicMock()
    writer.wait_closed = AsyncMock()
    return writer


# --- detect_socket candidate loop ---


def test_detect_socket_finds_candidate(tmp_path: pathlib.Path) -> None:
    sock = tmp_path / "podman" / "podman.sock"
    sock.parent.mkdir()
    sock.touch()
    with patch.dict(os.environ, {"POCKET_DOCK_SOCKET": "", "XDG_RUNTIME_DIR": str(tmp_path)}):
        result = detect_socket()
    assert result == str(sock)


# --- _read_headers edge cases ---


async def test_read_headers_line_without_colon() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"MalformedHeader\r\nContent-Type: text/plain\r\n\r\n")
    reader.feed_eof()
    headers = await _read_headers(reader)
    assert "content-type" in headers
    assert len(headers) == 1


# --- _read_chunked edge cases ---


async def test_read_chunked_with_empty_line() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"\r\n3\r\nabc\r\n0\r\n\r\n")
    reader.feed_eof()
    body = await _read_chunked(reader)
    assert body == b"abc"


# --- _request error handling ---


async def test_request_reraises_socket_connection_error() -> None:
    mock_writer = _make_mock_writer()
    mock_reader = asyncio.StreamReader()

    with (
        patch(
            "pocket_dock._socket_client._open_connection",
            new_callable=AsyncMock,
            return_value=(mock_reader, mock_writer),
        ),
        patch(
            "pocket_dock._socket_client._send_request",
            new_callable=AsyncMock,
            side_effect=SocketConnectionError("/tmp/s.sock", "test"),
        ),
        pytest.raises(SocketConnectionError),
    ):
        await _request("/tmp/s.sock", "GET", "/test")


async def test_request_wraps_oserror() -> None:
    mock_writer = _make_mock_writer()
    mock_reader = asyncio.StreamReader()

    with (
        patch(
            "pocket_dock._socket_client._open_connection",
            new_callable=AsyncMock,
            return_value=(mock_reader, mock_writer),
        ),
        patch(
            "pocket_dock._socket_client._send_request",
            new_callable=AsyncMock,
            side_effect=OSError("broken pipe"),
        ),
        pytest.raises(SocketCommunicationError, match="broken pipe"),
    ):
        await _request("/tmp/s.sock", "GET", "/test")


# --- _request_stream error handling ---


async def test_request_stream_cleans_up_on_exception() -> None:
    mock_writer = _make_mock_writer()
    mock_reader = asyncio.StreamReader()

    with (
        patch(
            "pocket_dock._socket_client._open_connection",
            new_callable=AsyncMock,
            return_value=(mock_reader, mock_writer),
        ),
        patch(
            "pocket_dock._socket_client._send_request",
            new_callable=AsyncMock,
            side_effect=OSError("connection reset"),
        ),
        pytest.raises(OSError, match="connection reset"),
    ):
        await _request_stream("/tmp/s.sock", "GET", "/test")

    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_awaited_once()


# --- _request_raw error handling ---


async def test_request_raw_reraises_socket_connection_error() -> None:
    mock_writer = _make_mock_writer()
    mock_reader = asyncio.StreamReader()

    with (
        patch(
            "pocket_dock._socket_client._open_connection",
            new_callable=AsyncMock,
            return_value=(mock_reader, mock_writer),
        ),
        patch(
            "pocket_dock._socket_client._send_request",
            new_callable=AsyncMock,
            side_effect=SocketConnectionError("/tmp/s.sock", "test"),
        ),
        pytest.raises(SocketConnectionError),
    ):
        await _request_raw("/tmp/s.sock", "PUT", "/test", b"data")


async def test_request_raw_wraps_oserror() -> None:
    mock_writer = _make_mock_writer()
    mock_reader = asyncio.StreamReader()

    with (
        patch(
            "pocket_dock._socket_client._open_connection",
            new_callable=AsyncMock,
            return_value=(mock_reader, mock_writer),
        ),
        patch(
            "pocket_dock._socket_client._send_request",
            new_callable=AsyncMock,
            side_effect=OSError("write error"),
        ),
        pytest.raises(SocketCommunicationError, match="write error"),
    ):
        await _request_raw("/tmp/s.sock", "PUT", "/test", b"data")


# --- ping ---


async def test_ping_failure() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(500, b"error"),
        ),
        pytest.raises(SocketCommunicationError, match="ping failed"),
    ):
        await ping("/tmp/s.sock")


# --- create_container ---


async def test_create_container_no_command_no_labels() -> None:
    with patch(
        "pocket_dock._socket_client._request",
        new_callable=AsyncMock,
        return_value=(201, b'{"Id": "abc123"}'),
    ):
        cid = await create_container("/tmp/s.sock", "test-image")
    assert cid == "abc123"


async def test_create_container_image_not_found() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(404, b"not found"),
        ),
        pytest.raises(ImageNotFound),
    ):
        await create_container("/tmp/s.sock", "no-such-image")


async def test_create_container_generic_error() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(500, b"internal error"),
        ),
        pytest.raises(SocketCommunicationError, match="create failed"),
    ):
        await create_container("/tmp/s.sock", "test-image")


# --- start_container ---


async def test_start_container_error() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(500, b"error"),
        ),
        pytest.raises(SocketCommunicationError),
    ):
        await start_container("/tmp/s.sock", "cid")


# --- stop_container ---


async def test_stop_container_error() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(500, b"error"),
        ),
        pytest.raises(SocketCommunicationError),
    ):
        await stop_container("/tmp/s.sock", "cid")


# --- remove_container ---


async def test_remove_container_error() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(500, b"error"),
        ),
        pytest.raises(SocketCommunicationError),
    ):
        await remove_container("/tmp/s.sock", "cid")


# --- _exec_create ---


async def test_exec_create_podman_500_container_state() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(500, b"container state improper"),
        ),
        pytest.raises(ContainerNotRunning),
    ):
        await _exec_create("/tmp/s.sock", "cid", ["echo", "hi"])


async def test_exec_create_generic_error() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(500, b"some other error"),
        ),
        pytest.raises(SocketCommunicationError, match="exec create failed"),
    ):
        await _exec_create("/tmp/s.sock", "cid", ["echo", "hi"])


# --- _exec_start ---


async def test_exec_start_error() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"error details")
    reader.feed_eof()
    mock_writer = _make_mock_writer()

    with (
        patch(
            "pocket_dock._socket_client._request_stream",
            new_callable=AsyncMock,
            return_value=(500, {}, reader, mock_writer),
        ),
        pytest.raises(SocketCommunicationError, match="exec start failed"),
    ):
        await _exec_start("/tmp/s.sock", "exec123", 10 * 1024 * 1024)


async def test_exec_start_non_chunked_stream() -> None:
    reader = asyncio.StreamReader()
    # stdout frame: type=1, 5 bytes
    reader.feed_data(struct.pack(">BxxxI", 1, 5))
    reader.feed_data(b"hello")
    reader.feed_eof()
    mock_writer = _make_mock_writer()

    with patch(
        "pocket_dock._socket_client._request_stream",
        new_callable=AsyncMock,
        return_value=(200, {}, reader, mock_writer),
    ):
        result = await _exec_start("/tmp/s.sock", "exec123", 10 * 1024 * 1024)

    assert result.stdout_text() == "hello"


async def test_exec_start_chunked_stream() -> None:
    # Build chunked body containing a multiplexed stdout frame
    frame = struct.pack(">BxxxI", 1, 3) + b"out"
    chunk_hex = f"{len(frame):x}".encode()
    chunked_body = chunk_hex + b"\r\n" + frame + b"\r\n0\r\n\r\n"

    reader = asyncio.StreamReader()
    reader.feed_data(chunked_body)
    reader.feed_eof()
    mock_writer = _make_mock_writer()

    with patch(
        "pocket_dock._socket_client._request_stream",
        new_callable=AsyncMock,
        return_value=(200, {"transfer-encoding": "chunked"}, reader, mock_writer),
    ):
        result = await _exec_start("/tmp/s.sock", "exec123", 10 * 1024 * 1024)

    assert result.stdout_text() == "out"


# --- _exec_inspect_exit_code ---


async def test_exec_inspect_exit_code_error() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(500, b"inspect error"),
        ),
        pytest.raises(SocketCommunicationError, match="exec inspect failed"),
    ):
        await _exec_inspect_exit_code("/tmp/s.sock", "exec123")


# --- push_archive ---


async def test_push_archive_404() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request_raw",
            new_callable=AsyncMock,
            return_value=(404, b"not found"),
        ),
        pytest.raises(FileNotFoundError, match="destination path not found"),
    ):
        await push_archive("/tmp/s.sock", "cid", "/no/such/dir", b"tardata")


# --- pull_archive ---


async def test_pull_archive_404() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(404, b"not found"),
        ),
        pytest.raises(FileNotFoundError, match="path not found"),
    ):
        await pull_archive("/tmp/s.sock", "cid", "/no/such/file")
