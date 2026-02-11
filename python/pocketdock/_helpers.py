# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Parsing and formatting utilities for container info and resource limits."""

from __future__ import annotations

import datetime
import re

from pocketdock.types import ContainerInfo

_KIB = 1024

_UNIT_MULTIPLIERS: dict[str, int] = {
    "b": 1,
    "k": _KIB,
    "m": _KIB**2,
    "g": _KIB**3,
    "t": _KIB**4,
}


def format_bytes(n: int) -> str:
    """Format a byte count as a human-readable string (e.g. ``42.1 MB``)."""
    if n < 0:
        return "0 B"
    value = float(n)
    units = ("B", "KB", "MB", "GB")
    for unit in units:
        if value < _KIB:
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= _KIB
    # Anything above GB is expressed in TB
    return f"{value:.1f} TB"


def parse_mem_limit(s: str) -> int:
    """Parse a memory limit string like ``256m`` or ``1g`` into bytes.

    Supports suffixes: ``b``, ``k``, ``m``, ``g``, ``t`` (case-insensitive).
    Plain integers are treated as bytes.
    """
    s = s.strip()
    match = re.fullmatch(r"(\d+)\s*([bkmgt])?", s, flags=re.IGNORECASE)
    if not match:
        msg = f"invalid memory limit: {s!r}"
        raise ValueError(msg)
    value = int(match.group(1))
    suffix = (match.group(2) or "b").lower()
    return value * _UNIT_MULTIPLIERS[suffix]


def parse_iso_timestamp(s: str) -> datetime.datetime:
    """Parse an ISO 8601 timestamp to a UTC datetime.

    Handles both ``Z`` suffix and ``+00:00`` offset, and truncates
    sub-microsecond precision that some engines emit.
    """
    s = s.replace("Z", "+00:00")
    # Truncate nanosecond precision — Python only handles microseconds
    # e.g. "2024-01-15T10:30:00.123456789+00:00" → "...123456+00:00"
    s = re.sub(r"(\.\d{6})\d+", r"\1", s)
    return datetime.datetime.fromisoformat(s)


def compute_cpu_percent(stats: dict[str, object]) -> float:
    """Compute CPU usage percentage from container stats."""
    try:
        cpu_stats = stats.get("cpu_stats", {})
        precpu_stats = stats.get("precpu_stats", {})
        if not isinstance(cpu_stats, dict) or not isinstance(precpu_stats, dict):
            return 0.0
        cpu_usage = cpu_stats.get("cpu_usage", {})
        precpu_usage = precpu_stats.get("cpu_usage", {})
        if not isinstance(cpu_usage, dict) or not isinstance(precpu_usage, dict):
            return 0.0
        cpu_delta = float(cpu_usage.get("total_usage", 0)) - float(
            precpu_usage.get("total_usage", 0)
        )
        system_delta = float(cpu_stats.get("system_cpu_usage", 0)) - float(
            precpu_stats.get("system_cpu_usage", 0)
        )
        online = cpu_stats.get("online_cpus", 0)
        if system_delta > 0 and isinstance(online, (int, float)) and online > 0:
            return round(cpu_delta / system_delta * float(online) * 100.0, 2)
    except (TypeError, ValueError, ArithmeticError):
        pass
    return 0.0


def _safe_dict(data: object, key: str) -> dict[str, object]:
    """Extract a dict sub-key from *data*, defaulting to ``{}``."""
    if not isinstance(data, dict):
        return {}
    val = data.get(key, {})
    return val if isinstance(val, dict) else {}


def _extract_memory(stats: dict[str, object] | None) -> tuple[str, str, float]:
    """Return ``(usage_str, limit_str, percent)`` from stats."""
    if stats is None:
        return "", "", 0.0
    mem = _safe_dict(stats, "memory_stats")
    usage_val = mem.get("usage", 0)
    limit_val = mem.get("limit", 0)
    if not isinstance(usage_val, (int, float)) or not isinstance(limit_val, (int, float)):
        return "", "", 0.0
    pct = round(float(usage_val) / float(limit_val) * 100.0, 2) if limit_val > 0 else 0.0
    return format_bytes(int(usage_val)), format_bytes(int(limit_val)), pct


def _extract_pids(stats: dict[str, object] | None) -> int:
    """Return the current PID count from stats."""
    if stats is None:
        return 0
    pids_stats = _safe_dict(stats, "pids_stats")
    current = pids_stats.get("current", 0)
    return int(current) if isinstance(current, (int, float)) else 0


def _extract_processes(top: dict[str, object] | None) -> tuple[dict[str, str], ...]:
    """Parse the ``top`` response into a tuple of process dicts."""
    if top is None:
        return ()
    titles = top.get("Titles", [])
    procs = top.get("Processes", [])
    if not isinstance(titles, list) or not isinstance(procs, list):
        return ()
    result: list[dict[str, str]] = []
    for proc in procs:
        if isinstance(proc, list):
            entry = {str(titles[i]): str(proc[i]) for i in range(min(len(titles), len(proc)))}
            result.append(entry)
    return tuple(result)


def build_container_info(
    inspect: dict[str, object],
    stats: dict[str, object] | None,
    top: dict[str, object] | None,
    name: str,
) -> ContainerInfo:
    """Assemble a :class:`ContainerInfo` from engine API responses."""
    state = _safe_dict(inspect, "State")
    config = _safe_dict(inspect, "Config")
    net = _safe_dict(inspect, "NetworkSettings")

    status = str(state.get("Status", "unknown"))
    created_at = parse_iso_timestamp(str(inspect.get("Created", "1970-01-01T00:00:00+00:00")))

    started_at: datetime.datetime | None = None
    uptime: datetime.timedelta | None = None
    started_str = state.get("StartedAt", "")
    if isinstance(started_str, str) and started_str and started_str != "0001-01-01T00:00:00Z":
        started_at = parse_iso_timestamp(started_str)
        if status == "running":
            uptime = datetime.datetime.now(tz=datetime.timezone.utc) - started_at

    mem_usage, mem_limit, mem_pct = _extract_memory(stats)
    ip_address = str(net.get("IPAddress", ""))

    return ContainerInfo(
        id=str(inspect.get("Id", "")),
        name=name,
        status=status,
        image=str(config.get("Image", "")),
        created_at=created_at,
        started_at=started_at,
        uptime=uptime,
        memory_usage=mem_usage,
        memory_limit=mem_limit,
        memory_percent=mem_pct,
        cpu_percent=compute_cpu_percent(stats) if stats is not None else 0.0,
        pids=_extract_pids(stats),
        network=bool(ip_address),
        ip_address=ip_address,
        processes=_extract_processes(top),
    )
