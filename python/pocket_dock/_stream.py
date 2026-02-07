# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Stream demultiplexing for Docker/Podman exec output.

The container engine's exec attach endpoint returns a multiplexed byte stream.
Each frame has an 8-byte header:
  - byte 0: stream type (1 = stdout, 2 = stderr)
  - bytes 1-3: padding (zero)
  - bytes 4-7: payload length (big-endian uint32)

This module parses that protocol into separate stdout/stderr buffers.
"""

from __future__ import annotations

import dataclasses
import struct
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio

STREAM_STDOUT = 1
STREAM_STDERR = 2
HEADER_SIZE = 8
_HEADER_FORMAT = ">BxxxI"  # 1 byte type, 3 padding, 4 byte length


def parse_stream_header(header: bytes) -> tuple[int, int]:
    """Parse an 8-byte Docker stream frame header.

    Returns:
        Tuple of (stream_type, payload_length).

    """
    stream_type, payload_length = struct.unpack(_HEADER_FORMAT, header)
    return stream_type, payload_length


@dataclasses.dataclass
class DemuxResult:
    """Result of demultiplexing a Docker exec stream."""

    stdout_bytes: bytes = b""
    stderr_bytes: bytes = b""
    truncated: bool = False

    def stdout_text(self) -> str:
        """Decode stdout bytes to string."""
        return self.stdout_bytes.decode("utf-8", errors="replace")

    def stderr_text(self) -> str:
        """Decode stderr bytes to string."""
        return self.stderr_bytes.decode("utf-8", errors="replace")


async def demux_stream(
    reader: asyncio.StreamReader,
    max_output: int = 10 * 1024 * 1024,
) -> DemuxResult:
    """Read a multiplexed Docker exec stream into separate stdout/stderr.

    Args:
        reader: Async stream reader connected to the exec attach endpoint.
        max_output: Maximum total bytes to accumulate before truncating.

    Returns:
        DemuxResult with stdout and stderr bytes.

    """
    stdout_parts: list[bytes] = []
    stderr_parts: list[bytes] = []
    total_bytes = 0
    truncated = False

    while True:
        header = await _read_exact(reader, HEADER_SIZE)
        if not header:
            break

        stream_type, payload_length = parse_stream_header(header)

        if payload_length == 0:
            continue

        payload = await _read_exact(reader, payload_length)
        if not payload:
            break

        if total_bytes + len(payload) > max_output:
            remaining = max_output - total_bytes
            if remaining > 0:
                payload = payload[:remaining]
            else:
                truncated = True
                break
            truncated = True

        total_bytes += len(payload)

        if stream_type == STREAM_STDOUT:
            stdout_parts.append(payload)
        elif stream_type == STREAM_STDERR:
            stderr_parts.append(payload)

        if truncated:
            break

    return DemuxResult(
        stdout_bytes=b"".join(stdout_parts),
        stderr_bytes=b"".join(stderr_parts),
        truncated=truncated,
    )


async def _read_exact(reader: asyncio.StreamReader, n: int) -> bytes:
    """Read exactly n bytes, returning empty bytes on EOF."""
    data = b""
    while len(data) < n:
        chunk = await reader.read(n - len(data))
        if not chunk:
            return b""
        data += chunk
    return data
