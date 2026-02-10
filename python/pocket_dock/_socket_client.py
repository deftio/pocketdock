# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Async HTTP-over-Unix-socket client for Podman/Docker.

Each function opens its own connection to the Unix socket, performs the
HTTP request, and closes the connection.  This is the connection-per-operation
model: Unix sockets are free, and isolation prevents streaming from blocking
other operations.

Uses unversioned Docker-compatible API paths (``/containers/create``, not
``/v4.0.0/libpod/...``) for Podman + Docker compatibility.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import time
import urllib.parse
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from pocket_dock._stream import (
    HEADER_SIZE as _DEMUX_HEADER_SIZE,
)
from pocket_dock._stream import (
    DemuxResult,
    demux_stream,
    demux_stream_iter,
    parse_stream_header,
)
from pocket_dock.errors import (
    ContainerNotFound,
    ContainerNotRunning,
    ImageNotFound,
    SocketCommunicationError,
    SocketConnectionError,
)
from pocket_dock.types import ExecResult

# ---------------------------------------------------------------------------
# Socket detection
# ---------------------------------------------------------------------------


def detect_socket() -> str | None:
    """Auto-detect an available container engine socket.

    Detection order:
    1. ``POCKET_DOCK_SOCKET`` env var
    2. Podman rootless: ``$XDG_RUNTIME_DIR/podman/podman.sock``
    3. Podman system: ``/run/podman/podman.sock``
    4. Docker: ``/var/run/docker.sock``

    Returns:
        The path to the first socket found, or ``None``.

    """
    explicit = os.environ.get("POCKET_DOCK_SOCKET")
    if explicit and pathlib.Path(explicit).exists():
        return explicit

    xdg = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    candidates = [
        pathlib.Path(xdg) / "podman" / "podman.sock",
        pathlib.Path("/run/podman/podman.sock"),
        pathlib.Path("/var/run/docker.sock"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


# ---------------------------------------------------------------------------
# Raw HTTP helpers
# ---------------------------------------------------------------------------


async def _open_connection(
    socket_path: str,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Open an async connection to a Unix socket."""
    try:
        return await asyncio.open_unix_connection(socket_path)
    except (OSError, ConnectionRefusedError) as exc:
        raise SocketConnectionError(socket_path, str(exc)) from exc


async def _send_request(
    writer: asyncio.StreamWriter,
    method: str,
    path: str,
    body: bytes | None = None,
    content_type: str = "application/json",
) -> None:
    """Write an HTTP/1.1 request to the writer."""
    lines = [
        f"{method} {path} HTTP/1.1",
        "Host: localhost",
    ]
    if body is not None:
        lines.append(f"Content-Type: {content_type}")
        lines.append(f"Content-Length: {len(body)}")
    lines.append("Connection: close")
    lines.append("")
    lines.append("")

    header_bytes = "\r\n".join(lines).encode("ascii")
    writer.write(header_bytes)
    if body is not None:
        writer.write(body)
    await writer.drain()


async def _read_status_line(reader: asyncio.StreamReader) -> int:
    """Read the HTTP status line and return the status code."""
    line = await reader.readline()
    if not line:
        msg = "empty response"
        raise SocketCommunicationError(msg)
    parts = line.decode("ascii", errors="replace").split(None, 2)
    if len(parts) < 2:  # noqa: PLR2004
        msg = f"malformed status line: {line!r}"
        raise SocketCommunicationError(msg)
    return int(parts[1])


async def _read_headers(reader: asyncio.StreamReader) -> dict[str, str]:
    """Read HTTP headers until the blank line."""
    headers: dict[str, str] = {}
    while True:
        line = await reader.readline()
        stripped = line.strip()
        if not stripped:
            break
        decoded = stripped.decode("ascii", errors="replace")
        if ":" in decoded:
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    return headers


async def _read_body(
    reader: asyncio.StreamReader,
    headers: dict[str, str],
) -> bytes:
    """Read the HTTP response body, handling Content-Length and chunked TE."""
    if headers.get("transfer-encoding", "").lower() == "chunked":
        return await _read_chunked(reader)

    content_length_str = headers.get("content-length")
    if content_length_str is not None:
        length = int(content_length_str)
        return await _read_exact_body(reader, length)

    # No Content-Length, no chunked: read until EOF
    parts: list[bytes] = []
    while True:
        chunk = await reader.read(65536)
        if not chunk:
            break
        parts.append(chunk)
    return b"".join(parts)


async def _read_exact_body(reader: asyncio.StreamReader, length: int) -> bytes:
    """Read exactly ``length`` bytes from the reader."""
    data = b""
    while len(data) < length:
        chunk = await reader.read(length - len(data))
        if not chunk:
            break
        data += chunk
    return data


async def _read_chunked(reader: asyncio.StreamReader) -> bytes:
    """Read a chunked transfer-encoded body."""
    parts: list[bytes] = []
    while True:
        size_line = await reader.readline()
        size_str = size_line.strip().decode("ascii", errors="replace")
        if not size_str:
            continue
        chunk_size = int(size_str, 16)
        if chunk_size == 0:
            await reader.readline()  # trailing \r\n
            break
        chunk_data = await _read_exact_body(reader, chunk_size)
        parts.append(chunk_data)
        await reader.readline()  # trailing \r\n after chunk
    return b"".join(parts)


async def _request(
    socket_path: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> tuple[int, bytes]:
    """Make an HTTP request and return (status_code, response_body).

    Opens a new connection per call.
    """
    reader, writer = await _open_connection(socket_path)
    try:
        body_bytes = json.dumps(body).encode("utf-8") if body is not None else None
        await _send_request(writer, method, path, body_bytes)

        status = await _read_status_line(reader)
        headers = await _read_headers(reader)
        response_body = await _read_body(reader, headers)
    except SocketConnectionError:
        raise
    except (OSError, asyncio.IncompleteReadError) as exc:
        raise SocketCommunicationError(str(exc)) from exc
    else:
        return status, response_body
    finally:
        writer.close()
        await writer.wait_closed()


async def _request_stream(
    socket_path: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, str], asyncio.StreamReader, asyncio.StreamWriter]:
    """Make an HTTP request and return (status, headers, reader, writer) for streaming.

    The caller is responsible for closing the writer.
    """
    reader, writer = await _open_connection(socket_path)
    try:
        body_bytes = json.dumps(body).encode("utf-8") if body is not None else None
        await _send_request(writer, method, path, body_bytes)

        status = await _read_status_line(reader)
        headers = await _read_headers(reader)
    except Exception:
        writer.close()
        await writer.wait_closed()
        raise
    else:
        return status, headers, reader, writer


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


def _check_container_response(
    status: int,
    body: bytes,
    container_id: str,
) -> None:
    """Raise appropriate errors based on HTTP status codes."""
    if status < 400:  # noqa: PLR2004
        return
    if status == 404:  # noqa: PLR2004
        raise ContainerNotFound(container_id)
    if status == 409:  # noqa: PLR2004
        raise ContainerNotRunning(container_id)
    msg = f"HTTP {status}: {body.decode('utf-8', errors='replace')}"
    raise SocketCommunicationError(msg)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def ping(socket_path: str) -> str:
    """Ping the container engine.

    Returns:
        ``"OK"`` on success.

    """
    status, body = await _request(socket_path, "GET", "/_ping")
    if status != 200:  # noqa: PLR2004
        msg = f"ping failed: HTTP {status}"
        raise SocketCommunicationError(msg)
    return body.decode("ascii").strip()


async def create_container(
    socket_path: str,
    image: str,
    command: list[str] | None = None,
    labels: dict[str, str] | None = None,
    host_config: dict[str, Any] | None = None,
) -> str:
    """Create a container and return its ID.

    Args:
        socket_path: Path to the container engine Unix socket.
        image: Image name to use.
        command: Command to run (default: image CMD).
        labels: OCI labels to attach.
        host_config: Docker-compatible ``HostConfig`` dict (resource limits, etc.).

    Returns:
        The container ID (full hex string).

    """
    payload: dict[str, Any] = {"Image": image}
    if command is not None:
        payload["Cmd"] = command
    if labels is not None:
        payload["Labels"] = labels
    if host_config is not None:
        payload["HostConfig"] = host_config

    status, body = await _request(socket_path, "POST", "/containers/create", payload)

    if status == 404:  # noqa: PLR2004
        raise ImageNotFound(image)
    if status >= 400:  # noqa: PLR2004
        msg = f"create failed: HTTP {status}: {body.decode('utf-8', errors='replace')}"
        raise SocketCommunicationError(msg)

    data = json.loads(body)
    return str(data["Id"])


async def start_container(socket_path: str, container_id: str) -> None:
    """Start a created container."""
    status, body = await _request(socket_path, "POST", f"/containers/{container_id}/start")
    # 204 = success, 304 = already started
    if status not in (204, 304):
        _check_container_response(status, body, container_id)


async def stop_container(socket_path: str, container_id: str, timeout: int = 10) -> None:
    """Stop a running container."""
    status, body = await _request(
        socket_path, "POST", f"/containers/{container_id}/stop?t={timeout}"
    )
    # 204 = success, 304 = already stopped
    if status not in (204, 304):
        _check_container_response(status, body, container_id)


async def remove_container(
    socket_path: str,
    container_id: str,
    *,
    force: bool = False,
) -> None:
    """Remove a container."""
    force_param = "true" if force else "false"
    status, body = await _request(
        socket_path,
        "DELETE",
        f"/containers/{container_id}?force={force_param}",
    )
    if status not in (200, 204):
        _check_container_response(status, body, container_id)


async def inspect_container(socket_path: str, container_id: str) -> dict[str, Any]:
    """Inspect a container, returning its full JSON state."""
    status, body = await _request(socket_path, "GET", f"/containers/{container_id}/json")
    _check_container_response(status, body, container_id)
    return json.loads(body)  # type: ignore[no-any-return]


async def get_container_stats(socket_path: str, container_id: str) -> dict[str, Any]:
    """Fetch a one-shot stats snapshot for a container.

    Uses ``GET /containers/{id}/stats?stream=false&one-shot=true``.
    """
    status, body = await _request(
        socket_path,
        "GET",
        f"/containers/{container_id}/stats?stream=false&one-shot=true",
    )
    _check_container_response(status, body, container_id)
    return json.loads(body)  # type: ignore[no-any-return]


async def get_container_top(socket_path: str, container_id: str) -> dict[str, Any]:
    """List running processes in a container.

    Uses ``GET /containers/{id}/top``.
    """
    status, body = await _request(
        socket_path,
        "GET",
        f"/containers/{container_id}/top",
    )
    _check_container_response(status, body, container_id)
    return json.loads(body)  # type: ignore[no-any-return]


async def restart_container(
    socket_path: str,
    container_id: str,
    timeout: int = 10,
) -> None:
    """Restart a container.

    Uses ``POST /containers/{id}/restart?t={timeout}``.
    """
    status, body = await _request(
        socket_path,
        "POST",
        f"/containers/{container_id}/restart?t={timeout}",
    )
    # 204 = success
    if status != 204:  # noqa: PLR2004
        _check_container_response(status, body, container_id)


async def exec_command(
    socket_path: str,
    container_id: str,
    command: list[str],
    max_output: int = 10 * 1024 * 1024,
    timeout: float | None = None,
) -> ExecResult:
    """Execute a command inside a running container.

    This performs three HTTP calls:
    1. Create exec instance (``POST /containers/{id}/exec``)
    2. Start exec and read multiplexed stream (``POST /exec/{id}/start``)
    3. Inspect exec to get exit code (``GET /exec/{id}/json``)

    Args:
        socket_path: Path to the container engine Unix socket.
        container_id: Container to exec into.
        command: Command and arguments.
        max_output: Maximum bytes to accumulate.
        timeout: Maximum seconds to wait for the command. ``None`` = no limit.

    Returns:
        ExecResult with exit code, stdout, stderr, and timing info.

    """
    start_time = time.monotonic()

    # Step 1: Create exec instance
    exec_id = await _exec_create(socket_path, container_id, command)

    # Step 2: Start exec and read stream (with optional timeout)
    timed_out = False
    try:
        if timeout is not None:
            demux_result = await asyncio.wait_for(
                _exec_start(socket_path, exec_id, max_output),
                timeout=timeout,
            )
        else:
            demux_result = await _exec_start(socket_path, exec_id, max_output)
    except (TimeoutError, asyncio.TimeoutError):
        timed_out = True
        demux_result = DemuxResult()

    # Step 3: Get exit code (skip if timed out — exec may still be running)
    if timed_out:
        exit_code = -1
    else:
        exit_code = await _exec_inspect_exit_code(socket_path, exec_id)

    duration_ms = (time.monotonic() - start_time) * 1000

    return ExecResult(
        exit_code=exit_code,
        stdout=demux_result.stdout_text(),
        stderr=demux_result.stderr_text(),
        duration_ms=duration_ms,
        timed_out=timed_out,
        truncated=demux_result.truncated,
    )


async def _exec_create(
    socket_path: str,
    container_id: str,
    command: list[str],
    *,
    attach_stdin: bool = False,
) -> str:
    """Create an exec instance and return its ID."""
    payload: dict[str, object] = {
        "AttachStdout": True,
        "AttachStderr": True,
        "Cmd": command,
    }
    if attach_stdin:
        payload["AttachStdin"] = True
    status, body = await _request(
        socket_path,
        "POST",
        f"/containers/{container_id}/exec",
        payload,
    )
    if status == 404:  # noqa: PLR2004
        raise ContainerNotFound(container_id)
    if status == 409:  # noqa: PLR2004
        raise ContainerNotRunning(container_id)
    if status >= 400:  # noqa: PLR2004
        body_text = body.decode("utf-8", errors="replace")
        # Podman returns 500 with "container state improper" for stopped containers
        if "container state improper" in body_text:
            raise ContainerNotRunning(container_id)
        msg = f"exec create failed: HTTP {status}: {body_text}"
        raise SocketCommunicationError(msg)

    data = json.loads(body)
    return str(data["Id"])


async def _exec_start(
    socket_path: str,
    exec_id: str,
    max_output: int,
) -> DemuxResult:
    """Start an exec instance and read the multiplexed stream."""
    payload = {"Detach": False, "Tty": False}
    status, headers, reader, writer = await _request_stream(
        socket_path,
        "POST",
        f"/exec/{exec_id}/start",
        payload,
    )
    try:
        if status >= 400:  # noqa: PLR2004
            rest = await reader.read(65536)
            msg = f"exec start failed: HTTP {status}: {rest.decode('utf-8', errors='replace')}"
            raise SocketCommunicationError(msg)

        # Docker wraps the multiplexed stream in chunked transfer encoding;
        # Podman sends the raw multiplexed stream directly.
        if headers.get("transfer-encoding", "").lower() == "chunked":
            raw = await _read_chunked(reader)
            mem_reader = asyncio.StreamReader()
            mem_reader.feed_data(raw)
            mem_reader.feed_eof()
            return await demux_stream(mem_reader, max_output)
        return await demux_stream(reader, max_output)
    finally:
        writer.close()
        await writer.wait_closed()


async def _exec_start_stream(
    socket_path: str,
    exec_id: str,
) -> tuple[AsyncGenerator[tuple[int, bytes], None], asyncio.StreamWriter]:
    """Start an exec and return a (frame_generator, writer) pair for streaming.

    The caller must close the writer when done.  Handles both Docker (chunked
    transfer encoding) and Podman (raw multiplexed stream).
    """
    payload = {"Detach": False, "Tty": False}
    status, headers, reader, writer = await _request_stream(
        socket_path,
        "POST",
        f"/exec/{exec_id}/start",
        payload,
    )
    if status >= 400:  # noqa: PLR2004
        rest = await reader.read(65536)
        writer.close()
        await writer.wait_closed()
        msg = f"exec start failed: HTTP {status}: {rest.decode('utf-8', errors='replace')}"
        raise SocketCommunicationError(msg)

    is_chunked = headers.get("transfer-encoding", "").lower() == "chunked"
    if is_chunked:
        gen: AsyncGenerator[tuple[int, bytes], None] = _demux_chunked_stream(reader)
    else:
        gen = demux_stream_iter(reader)
    return gen, writer


async def _demux_chunked_stream(
    reader: asyncio.StreamReader,
) -> AsyncGenerator[tuple[int, bytes], None]:
    """Parse multiplexed frames from a chunked transfer-encoded stream.

    HTTP chunk boundaries may not align with demux frame boundaries, so we
    accumulate unchunked data and parse complete frames from it.
    """
    buf = bytearray()
    while True:
        size_line = await reader.readline()
        size_str = size_line.strip().decode("ascii", errors="replace")
        if not size_str:
            continue
        chunk_size = int(size_str, 16)
        if chunk_size == 0:
            await reader.readline()  # trailing CRLF
            break
        chunk_data = await _read_exact_body(reader, chunk_size)
        await reader.readline()  # trailing CRLF after chunk
        buf.extend(chunk_data)

        # Parse all complete demux frames from the accumulated buffer
        while len(buf) >= _DEMUX_HEADER_SIZE:
            stream_type, payload_length = parse_stream_header(bytes(buf[:_DEMUX_HEADER_SIZE]))
            total_frame = _DEMUX_HEADER_SIZE + payload_length
            if len(buf) < total_frame:
                break
            payload = bytes(buf[_DEMUX_HEADER_SIZE:total_frame])
            del buf[:total_frame]
            if payload_length > 0:
                yield stream_type, payload


async def _exec_inspect_exit_code(socket_path: str, exec_id: str) -> int:
    """Inspect an exec instance and return its exit code."""
    status, body = await _request(socket_path, "GET", f"/exec/{exec_id}/json")
    if status >= 400:  # noqa: PLR2004
        msg = f"exec inspect failed: HTTP {status}: {body.decode('utf-8', errors='replace')}"
        raise SocketCommunicationError(msg)
    data = json.loads(body)
    return int(data["ExitCode"])


# ---------------------------------------------------------------------------
# Raw request (for binary bodies like tar archives)
# ---------------------------------------------------------------------------


async def _request_raw(
    socket_path: str,
    method: str,
    path: str,
    body: bytes | None = None,
    content_type: str = "application/x-tar",
) -> tuple[int, bytes]:
    """Make an HTTP request with a raw byte body."""
    reader, writer = await _open_connection(socket_path)
    try:
        await _send_request(writer, method, path, body, content_type=content_type)
        status = await _read_status_line(reader)
        headers = await _read_headers(reader)
        response_body = await _read_body(reader, headers)
    except SocketConnectionError:
        raise
    except (OSError, asyncio.IncompleteReadError) as exc:
        raise SocketCommunicationError(str(exc)) from exc
    else:
        return status, response_body
    finally:
        writer.close()
        await writer.wait_closed()


# ---------------------------------------------------------------------------
# Archive API (file push/pull)
# ---------------------------------------------------------------------------


async def push_archive(
    socket_path: str,
    container_id: str,
    dest_path: str,
    tar_data: bytes,
) -> None:
    """Upload a tar archive to the container.

    Uses ``PUT /containers/{id}/archive?path={dest}``.

    Args:
        socket_path: Path to the container engine Unix socket.
        container_id: Target container ID.
        dest_path: Destination directory inside the container.
        tar_data: Raw tar archive bytes.

    """
    encoded_path = urllib.parse.quote(dest_path, safe="")
    status, body = await _request_raw(
        socket_path,
        "PUT",
        f"/containers/{container_id}/archive?path={encoded_path}",
        tar_data,
    )
    if status == 404:  # noqa: PLR2004
        msg = f"destination path not found in container: {dest_path}"
        raise FileNotFoundError(msg)
    _check_container_response(status, body, container_id)


async def pull_archive(
    socket_path: str,
    container_id: str,
    src_path: str,
) -> bytes:
    """Download a tar archive from the container.

    Uses ``GET /containers/{id}/archive?path={src}``.

    Args:
        socket_path: Path to the container engine Unix socket.
        container_id: Source container ID.
        src_path: Path inside the container to download.

    Returns:
        Raw tar archive bytes.

    Raises:
        FileNotFoundError: If the path does not exist inside the container.

    """
    encoded_path = urllib.parse.quote(src_path, safe="")
    status, body = await _request(
        socket_path,
        "GET",
        f"/containers/{container_id}/archive?path={encoded_path}",
    )
    if status == 404:  # noqa: PLR2004
        msg = f"path not found in container: {src_path}"
        raise FileNotFoundError(msg)
    _check_container_response(status, body, container_id)
    return body


# ---------------------------------------------------------------------------
# Container listing / commit
# ---------------------------------------------------------------------------


async def list_containers(
    socket_path: str,
    *,
    label_filter: str | None = None,
) -> list[dict[str, Any]]:
    """List containers, optionally filtered by label.

    Uses ``GET /containers/json?all=true``.

    Args:
        socket_path: Path to the container engine Unix socket.
        label_filter: Label filter string (e.g. ``"pocket-dock.managed=true"``).

    Returns:
        List of container JSON objects from the engine.

    """
    path = "/containers/json?all=true"
    if label_filter is not None:
        filters = json.dumps({"label": [label_filter]})
        path = f"{path}&filters={urllib.parse.quote(filters)}"
    status, body = await _request(socket_path, "GET", path)
    if status >= 400:  # noqa: PLR2004
        msg = f"list containers failed: HTTP {status}: {body.decode('utf-8', errors='replace')}"
        raise SocketCommunicationError(msg)
    return json.loads(body)  # type: ignore[no-any-return]


async def commit_container(
    socket_path: str,
    container_id: str,
    repo: str,
    tag: str,
) -> str:
    """Commit a container's filesystem as a new image.

    Uses ``POST /commit?container={id}&repo={repo}&tag={tag}``.

    Args:
        socket_path: Path to the container engine Unix socket.
        container_id: Container to commit.
        repo: Image repository name.
        tag: Image tag.

    Returns:
        The new image ID.

    """
    params = urllib.parse.urlencode(
        {
            "container": container_id,
            "repo": repo,
            "tag": tag,
        }
    )
    status, body = await _request(socket_path, "POST", f"/commit?{params}")
    _check_container_response(status, body, container_id)
    data = json.loads(body)
    return str(data["Id"])
