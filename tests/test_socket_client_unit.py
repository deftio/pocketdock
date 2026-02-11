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
    _demux_chunked_stream,
    _exec_create,
    _exec_inspect_exit_code,
    _exec_start,
    _exec_start_stream,
    _read_body,
    _read_chunked,
    _read_exact_body,
    _read_headers,
    _read_status_line,
    _request,
    _request_raw,
    _request_stream,
    _send_request,
    build_image,
    commit_container,
    create_container,
    detect_socket,
    get_container_stats,
    get_container_top,
    list_containers,
    load_image,
    ping,
    pull_archive,
    push_archive,
    remove_container,
    restart_container,
    save_image,
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


async def test_exec_create_404() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(404, b"not found"),
        ),
        pytest.raises(ContainerNotFound),
    ):
        await _exec_create("/tmp/s.sock", "cid", ["echo", "hi"])


async def test_exec_create_409() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(409, b"not running"),
        ),
        pytest.raises(ContainerNotRunning),
    ):
        await _exec_create("/tmp/s.sock", "cid", ["echo", "hi"])


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


# --- get_container_stats ---


async def test_get_container_stats_success() -> None:
    stats_json = b'{"memory_stats":{"usage":1024}}'
    with patch(
        "pocket_dock._socket_client._request",
        new_callable=AsyncMock,
        return_value=(200, stats_json),
    ):
        result = await get_container_stats("/tmp/s.sock", "cid")
    assert result["memory_stats"]["usage"] == 1024


async def test_get_container_stats_not_found() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(404, b"not found"),
        ),
        pytest.raises(ContainerNotFound),
    ):
        await get_container_stats("/tmp/s.sock", "cid")


async def test_get_container_stats_not_running() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(409, b"not running"),
        ),
        pytest.raises(ContainerNotRunning),
    ):
        await get_container_stats("/tmp/s.sock", "cid")


# --- get_container_top ---


async def test_get_container_top_success() -> None:
    top_json = b'{"Titles":["PID"],"Processes":[["1"]]}'
    with patch(
        "pocket_dock._socket_client._request",
        new_callable=AsyncMock,
        return_value=(200, top_json),
    ):
        result = await get_container_top("/tmp/s.sock", "cid")
    assert result["Titles"] == ["PID"]


async def test_get_container_top_not_running() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(409, b"not running"),
        ),
        pytest.raises(ContainerNotRunning),
    ):
        await get_container_top("/tmp/s.sock", "cid")


# --- restart_container ---


async def test_restart_container_success() -> None:
    with patch(
        "pocket_dock._socket_client._request",
        new_callable=AsyncMock,
        return_value=(204, b""),
    ):
        await restart_container("/tmp/s.sock", "cid")


async def test_restart_container_not_found() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(404, b"not found"),
        ),
        pytest.raises(ContainerNotFound),
    ):
        await restart_container("/tmp/s.sock", "cid")


async def test_restart_container_custom_timeout() -> None:
    with patch(
        "pocket_dock._socket_client._request",
        new_callable=AsyncMock,
        return_value=(204, b""),
    ) as mock_req:
        await restart_container("/tmp/s.sock", "cid", timeout=30)
    # Verify the timeout is in the URL
    call_args = mock_req.call_args[0]
    assert "t=30" in call_args[2]


# --- create_container with host_config ---


async def test_create_container_with_host_config() -> None:
    with patch(
        "pocket_dock._socket_client._request",
        new_callable=AsyncMock,
        return_value=(201, b'{"Id": "abc123"}'),
    ) as mock_req:
        cid = await create_container(
            "/tmp/s.sock",
            "test-image",
            host_config={"Memory": 256 * 1024 * 1024},
        )
    assert cid == "abc123"
    payload = mock_req.call_args[0][3]
    assert payload["HostConfig"]["Memory"] == 256 * 1024 * 1024


async def test_create_container_no_host_config() -> None:
    with patch(
        "pocket_dock._socket_client._request",
        new_callable=AsyncMock,
        return_value=(201, b'{"Id": "abc123"}'),
    ) as mock_req:
        await create_container("/tmp/s.sock", "test-image")
    payload = mock_req.call_args[0][3]
    assert "HostConfig" not in payload


# --- _demux_chunked_stream ---


def _make_frame(stream_type: int, data: bytes) -> bytes:
    """Build a Docker stream multiplexed frame."""
    return struct.pack(">BxxxI", stream_type, len(data)) + data


def _make_chunked_body(*chunks: bytes) -> bytes:
    """Build a chunked transfer-encoded body from raw data chunks."""
    parts: list[bytes] = []
    for chunk in chunks:
        parts.append(f"{len(chunk):x}\r\n".encode())
        parts.append(chunk)
        parts.append(b"\r\n")
    parts.append(b"0\r\n\r\n")
    return b"".join(parts)


async def test_demux_chunked_stream_single_frame() -> None:
    frame = _make_frame(1, b"hello\n")
    body = _make_chunked_body(frame)
    reader = asyncio.StreamReader()
    reader.feed_data(body)
    reader.feed_eof()

    frames = [(st, p) async for st, p in _demux_chunked_stream(reader)]
    assert frames == [(1, b"hello\n")]


async def test_demux_chunked_stream_multiple_frames_in_one_chunk() -> None:
    frame1 = _make_frame(1, b"out\n")
    frame2 = _make_frame(2, b"err\n")
    body = _make_chunked_body(frame1 + frame2)
    reader = asyncio.StreamReader()
    reader.feed_data(body)
    reader.feed_eof()

    frames = [(st, p) async for st, p in _demux_chunked_stream(reader)]
    assert len(frames) == 2
    assert frames[0] == (1, b"out\n")
    assert frames[1] == (2, b"err\n")


async def test_demux_chunked_stream_frame_split_across_chunks() -> None:
    frame = _make_frame(1, b"split data")
    # Split the frame in the middle
    mid = len(frame) // 2
    body = _make_chunked_body(frame[:mid], frame[mid:])
    reader = asyncio.StreamReader()
    reader.feed_data(body)
    reader.feed_eof()

    frames = [(st, p) async for st, p in _demux_chunked_stream(reader)]
    assert frames == [(1, b"split data")]


async def test_demux_chunked_stream_empty() -> None:
    _make_chunked_body()  # just "0\r\n\r\n"
    reader = asyncio.StreamReader()
    reader.feed_data(b"0\r\n\r\n")
    reader.feed_eof()

    frames = [(st, p) async for st, p in _demux_chunked_stream(reader)]
    assert frames == []


async def test_demux_chunked_stream_zero_length_frame() -> None:
    """Zero-length demux frame inside a chunk should be skipped."""
    zero_frame = struct.pack(">BxxxI", 1, 0)  # stdout, 0 bytes
    real_frame = _make_frame(1, b"after zero\n")
    chunk = zero_frame + real_frame
    body = _make_chunked_body(chunk)
    reader = asyncio.StreamReader()
    reader.feed_data(body)
    reader.feed_eof()

    frames = [(st, p) async for st, p in _demux_chunked_stream(reader)]
    assert frames == [(1, b"after zero\n")]


async def test_demux_chunked_stream_empty_lines_between_chunks() -> None:
    """Empty lines between chunk size lines should be skipped."""
    frame = _make_frame(1, b"hello\n")
    chunk_hex = f"{len(frame):x}\r\n".encode()
    # Insert an empty line before the chunk size
    body = b"\r\n" + chunk_hex + frame + b"\r\n" + b"0\r\n\r\n"
    reader = asyncio.StreamReader()
    reader.feed_data(body)
    reader.feed_eof()

    frames = [(st, p) async for st, p in _demux_chunked_stream(reader)]
    assert frames == [(1, b"hello\n")]


async def test_demux_chunked_stream_eof_without_terminal_chunk() -> None:
    """EOF (connection closed) without a terminal 0-size chunk should not hang."""
    frame = _make_frame(1, b"before eof\n")
    chunk_hex = f"{len(frame):x}\r\n".encode()
    # No terminal "0\r\n\r\n" — just data then EOF
    body = chunk_hex + frame + b"\r\n"
    reader = asyncio.StreamReader()
    reader.feed_data(body)
    reader.feed_eof()

    frames = [(st, p) async for st, p in _demux_chunked_stream(reader)]
    assert frames == [(1, b"before eof\n")]


# --- _exec_start_stream ---


async def test_exec_start_stream_podman_raw() -> None:
    """Test streaming with Podman (raw multiplexed, no chunked TE)."""
    frame = _make_frame(1, b"hello\n")
    reader = asyncio.StreamReader()
    reader.feed_data(frame)
    reader.feed_eof()

    mock_writer = MagicMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()

    with patch(
        "pocket_dock._socket_client._request_stream",
        new_callable=AsyncMock,
        return_value=(200, {}, reader, mock_writer),
    ):
        gen, writer = await _exec_start_stream("/tmp/s.sock", "exec-id")
        frames = [(st, p) async for st, p in gen]

    assert frames == [(1, b"hello\n")]
    assert writer is mock_writer


async def test_exec_start_stream_docker_chunked() -> None:
    """Test streaming with Docker (chunked transfer encoding)."""
    frame = _make_frame(1, b"chunked hello\n")
    body = _make_chunked_body(frame)
    reader = asyncio.StreamReader()
    reader.feed_data(body)
    reader.feed_eof()

    mock_writer = MagicMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()

    with patch(
        "pocket_dock._socket_client._request_stream",
        new_callable=AsyncMock,
        return_value=(200, {"transfer-encoding": "chunked"}, reader, mock_writer),
    ):
        gen, _writer = await _exec_start_stream("/tmp/s.sock", "exec-id")
        frames = [(st, p) async for st, p in gen]

    assert frames == [(1, b"chunked hello\n")]


async def test_exec_start_stream_error_status() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"container not found")
    reader.feed_eof()

    mock_writer = MagicMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()

    with (
        patch(
            "pocket_dock._socket_client._request_stream",
            new_callable=AsyncMock,
            return_value=(404, {}, reader, mock_writer),
        ),
        pytest.raises(SocketCommunicationError, match="exec start failed"),
    ):
        await _exec_start_stream("/tmp/s.sock", "exec-id")


# --- list_containers ---


async def test_list_containers_no_filter() -> None:
    import json

    result_body = json.dumps([{"Id": "abc", "State": "running"}]).encode()
    with patch(
        "pocket_dock._socket_client._request",
        new_callable=AsyncMock,
        return_value=(200, result_body),
    ) as mock:
        result = await list_containers("/tmp/s.sock")

    assert len(result) == 1
    assert result[0]["Id"] == "abc"
    call_path = mock.call_args[0][2]
    assert call_path == "/containers/json?all=true"


async def test_list_containers_with_label_filter() -> None:
    import json
    import urllib.parse

    result_body = json.dumps([]).encode()
    with patch(
        "pocket_dock._socket_client._request",
        new_callable=AsyncMock,
        return_value=(200, result_body),
    ) as mock:
        result = await list_containers(
            "/tmp/s.sock",
            label_filter="pocket-dock.managed=true",
        )

    assert result == []
    call_path = mock.call_args[0][2]
    assert "filters=" in call_path
    decoded = urllib.parse.unquote(call_path)
    assert "pocket-dock.managed=true" in decoded


async def test_list_containers_error() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(500, b"internal error"),
        ),
        pytest.raises(SocketCommunicationError, match="list containers failed"),
    ):
        await list_containers("/tmp/s.sock")


# --- commit_container ---


async def test_commit_container_success() -> None:
    import json

    result_body = json.dumps({"Id": "sha256:newimage123"}).encode()
    with patch(
        "pocket_dock._socket_client._request",
        new_callable=AsyncMock,
        return_value=(201, result_body),
    ) as mock:
        image_id = await commit_container("/tmp/s.sock", "cid123", "myrepo", "v1")

    assert image_id == "sha256:newimage123"
    call_path = mock.call_args[0][2]
    assert "container=cid123" in call_path
    assert "repo=myrepo" in call_path
    assert "tag=v1" in call_path


async def test_commit_container_not_found() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(404, b"not found"),
        ),
        pytest.raises(ContainerNotFound),
    ):
        await commit_container("/tmp/s.sock", "cid", "repo", "tag")


async def test_commit_container_not_running() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request",
            new_callable=AsyncMock,
            return_value=(409, b"conflict"),
        ),
        pytest.raises(ContainerNotRunning),
    ):
        await commit_container("/tmp/s.sock", "cid", "repo", "tag")


# --- build_image ---


async def test_build_image_success() -> None:
    with patch(
        "pocket_dock._socket_client._request_raw",
        new_callable=AsyncMock,
        return_value=(200, b'{"stream":"Step 1/1 : FROM alpine"}'),
    ):
        result = await build_image("/tmp/s.sock", b"tar-data", "pocket-dock/test")
    assert "Step 1/1" in result


async def test_build_image_error() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request_raw",
            new_callable=AsyncMock,
            return_value=(500, b"build error"),
        ),
        pytest.raises(SocketCommunicationError, match="build failed"),
    ):
        await build_image("/tmp/s.sock", b"tar", "bad:tag")


# --- save_image ---


async def test_save_image_success() -> None:
    fake_tar = b"fake-tar-bytes"
    with patch(
        "pocket_dock._socket_client._request_raw",
        new_callable=AsyncMock,
        return_value=(200, fake_tar),
    ):
        result = await save_image("/tmp/s.sock", "pocket-dock/minimal")
    assert result == fake_tar


async def test_save_image_not_found() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request_raw",
            new_callable=AsyncMock,
            return_value=(404, b"not found"),
        ),
        pytest.raises(ImageNotFound),
    ):
        await save_image("/tmp/s.sock", "nonexistent:latest")


async def test_save_image_error() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request_raw",
            new_callable=AsyncMock,
            return_value=(500, b"server error"),
        ),
        pytest.raises(SocketCommunicationError, match="save failed"),
    ):
        await save_image("/tmp/s.sock", "bad:image")


# --- load_image ---


async def test_load_image_success() -> None:
    with patch(
        "pocket_dock._socket_client._request_raw",
        new_callable=AsyncMock,
        return_value=(200, b'{"stream":"Loaded image"}'),
    ):
        result = await load_image("/tmp/s.sock", b"tar-data")
    assert "Loaded image" in result


async def test_load_image_error() -> None:
    with (
        patch(
            "pocket_dock._socket_client._request_raw",
            new_callable=AsyncMock,
            return_value=(500, b"load error"),
        ),
        pytest.raises(SocketCommunicationError, match="load failed"),
    ):
        await load_image("/tmp/s.sock", b"bad-tar")
