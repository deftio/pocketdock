"""Unit tests for _helpers parsing and formatting utilities."""

from __future__ import annotations

import datetime

import pytest
from pocketdock._helpers import (
    _extract_memory,
    _extract_pids,
    _extract_processes,
    _safe_dict,
    build_container_info,
    build_exposed_ports,
    build_port_bindings,
    compute_cpu_percent,
    format_bytes,
    parse_iso_timestamp,
    parse_mem_limit,
    parse_port_bindings,
)

# --- format_bytes ---


def test_format_bytes_zero() -> None:
    assert format_bytes(0) == "0 B"


def test_format_bytes_negative() -> None:
    assert format_bytes(-1) == "0 B"


def test_format_bytes_small() -> None:
    assert format_bytes(512) == "512 B"


def test_format_bytes_kb() -> None:
    assert format_bytes(1024) == "1.0 KB"


def test_format_bytes_mb() -> None:
    assert format_bytes(42 * 1024 * 1024) == "42.0 MB"


def test_format_bytes_gb() -> None:
    assert format_bytes(2 * 1024**3) == "2.0 GB"


def test_format_bytes_tb() -> None:
    assert format_bytes(3 * 1024**4) == "3.0 TB"


def test_format_bytes_large_tb() -> None:
    # Values beyond TB still use TB
    assert "TB" in format_bytes(100 * 1024**4)


# --- parse_mem_limit ---


def test_parse_mem_limit_plain_bytes() -> None:
    assert parse_mem_limit("1024") == 1024


def test_parse_mem_limit_b_suffix() -> None:
    assert parse_mem_limit("512b") == 512


def test_parse_mem_limit_k_suffix() -> None:
    assert parse_mem_limit("4k") == 4096


def test_parse_mem_limit_m_suffix() -> None:
    assert parse_mem_limit("256m") == 256 * 1024**2


def test_parse_mem_limit_g_suffix() -> None:
    assert parse_mem_limit("1G") == 1024**3


def test_parse_mem_limit_t_suffix() -> None:
    assert parse_mem_limit("1t") == 1024**4


def test_parse_mem_limit_with_spaces() -> None:
    assert parse_mem_limit("  128 m  ") == 128 * 1024**2


def test_parse_mem_limit_invalid() -> None:
    with pytest.raises(ValueError, match="invalid memory limit"):
        parse_mem_limit("abc")


def test_parse_mem_limit_empty() -> None:
    with pytest.raises(ValueError, match="invalid memory limit"):
        parse_mem_limit("")


# --- parse_iso_timestamp ---


def test_parse_iso_timestamp_z_suffix() -> None:
    dt = parse_iso_timestamp("2026-01-15T10:30:00Z")
    assert dt == datetime.datetime(2026, 1, 15, 10, 30, tzinfo=datetime.timezone.utc)


def test_parse_iso_timestamp_offset() -> None:
    dt = parse_iso_timestamp("2026-01-15T10:30:00+00:00")
    assert dt == datetime.datetime(2026, 1, 15, 10, 30, tzinfo=datetime.timezone.utc)


def test_parse_iso_timestamp_nanoseconds() -> None:
    dt = parse_iso_timestamp("2026-01-15T10:30:00.123456789+00:00")
    assert dt.microsecond == 123456


def test_parse_iso_timestamp_microseconds() -> None:
    dt = parse_iso_timestamp("2026-01-15T10:30:00.654321+00:00")
    assert dt.microsecond == 654321


# --- compute_cpu_percent ---


def test_compute_cpu_percent_normal() -> None:
    stats = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 200},
            "system_cpu_usage": 1000,
            "online_cpus": 4,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 100},
            "system_cpu_usage": 500,
        },
    }
    result = compute_cpu_percent(stats)
    # (200-100)/(1000-500)*4*100 = 80.0
    assert result == 80.0


def test_compute_cpu_percent_zero_system_delta() -> None:
    stats = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 100},
            "system_cpu_usage": 500,
            "online_cpus": 4,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 100},
            "system_cpu_usage": 500,
        },
    }
    assert compute_cpu_percent(stats) == 0.0


def test_compute_cpu_percent_empty_stats() -> None:
    assert compute_cpu_percent({}) == 0.0


def test_compute_cpu_percent_non_dict_cpu_stats() -> None:
    assert compute_cpu_percent({"cpu_stats": "not a dict"}) == 0.0


def test_compute_cpu_percent_non_dict_cpu_usage() -> None:
    stats = {
        "cpu_stats": {"cpu_usage": "bad"},
        "precpu_stats": {"cpu_usage": {}},
    }
    assert compute_cpu_percent(stats) == 0.0


def test_compute_cpu_percent_zero_online_cpus() -> None:
    stats = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 200},
            "system_cpu_usage": 1000,
            "online_cpus": 0,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 100},
            "system_cpu_usage": 500,
        },
    }
    assert compute_cpu_percent(stats) == 0.0


def test_compute_cpu_percent_type_error() -> None:
    stats = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": "not_a_number"},
            "system_cpu_usage": 1000,
            "online_cpus": 4,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 100},
            "system_cpu_usage": 500,
        },
    }
    assert compute_cpu_percent(stats) == 0.0


# --- _safe_dict ---


def test_safe_dict_normal() -> None:
    data: dict[str, object] = {"key": {"nested": "value"}}
    assert _safe_dict(data, "key") == {"nested": "value"}


def test_safe_dict_missing_key() -> None:
    assert _safe_dict({"a": 1}, "b") == {}


def test_safe_dict_non_dict_data() -> None:
    assert _safe_dict("not a dict", "key") == {}


def test_safe_dict_non_dict_value() -> None:
    assert _safe_dict({"key": "string_val"}, "key") == {}


# --- _extract_memory ---


def test_extract_memory_none_stats() -> None:
    assert _extract_memory(None) == ("", "", 0.0)


def test_extract_memory_normal() -> None:
    stats: dict[str, object] = {
        "memory_stats": {"usage": 42 * 1024 * 1024, "limit": 256 * 1024 * 1024}
    }
    usage, limit, pct = _extract_memory(stats)
    assert usage == "42.0 MB"
    assert limit == "256.0 MB"
    assert pct == pytest.approx(16.41, abs=0.01)


def test_extract_memory_zero_limit() -> None:
    stats: dict[str, object] = {"memory_stats": {"usage": 100, "limit": 0}}
    _, _, pct = _extract_memory(stats)
    assert pct == 0.0


def test_extract_memory_non_numeric() -> None:
    stats: dict[str, object] = {"memory_stats": {"usage": "bad", "limit": 100}}
    assert _extract_memory(stats) == ("", "", 0.0)


# --- _extract_pids ---


def test_extract_pids_none() -> None:
    assert _extract_pids(None) == 0


def test_extract_pids_normal() -> None:
    stats: dict[str, object] = {"pids_stats": {"current": 5}}
    assert _extract_pids(stats) == 5


def test_extract_pids_non_numeric() -> None:
    stats: dict[str, object] = {"pids_stats": {"current": "bad"}}
    assert _extract_pids(stats) == 0


# --- _extract_processes ---


def test_extract_processes_none() -> None:
    assert _extract_processes(None) == ()


def test_extract_processes_normal() -> None:
    top: dict[str, object] = {
        "Titles": ["PID", "CMD"],
        "Processes": [["1", "sleep"], ["2", "bash"]],
    }
    procs = _extract_processes(top)
    assert len(procs) == 2
    assert procs[0] == {"PID": "1", "CMD": "sleep"}


def test_extract_processes_non_list_titles() -> None:
    top: dict[str, object] = {"Titles": "bad", "Processes": []}
    assert _extract_processes(top) == ()


def test_extract_processes_non_list_proc_entry() -> None:
    top: dict[str, object] = {
        "Titles": ["PID"],
        "Processes": ["not_a_list", ["1"]],
    }
    procs = _extract_processes(top)
    assert len(procs) == 1


# --- build_container_info ---


def test_build_container_info_running() -> None:
    inspect: dict[str, object] = {
        "Id": "abc123",
        "Created": "2026-01-01T00:00:00Z",
        "State": {
            "Status": "running",
            "Running": True,
            "StartedAt": "2026-01-01T00:01:00Z",
        },
        "Config": {"Image": "test-image"},
        "NetworkSettings": {"IPAddress": "172.17.0.2"},
    }
    stats: dict[str, object] = {
        "memory_stats": {"usage": 1024, "limit": 4096},
        "pids_stats": {"current": 2},
        "cpu_stats": {
            "cpu_usage": {"total_usage": 200},
            "system_cpu_usage": 1000,
            "online_cpus": 4,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 100},
            "system_cpu_usage": 500,
        },
    }
    top: dict[str, object] = {
        "Titles": ["PID", "CMD"],
        "Processes": [["1", "sleep"]],
    }
    info = build_container_info(inspect, stats, top, "pd-test")
    assert info.id == "abc123"
    assert info.status == "running"
    assert info.image == "test-image"
    assert info.started_at is not None
    assert info.uptime is not None
    assert info.pids == 2
    assert info.network is True
    assert info.ip_address == "172.17.0.2"
    assert len(info.processes) == 1


def test_build_container_info_stopped() -> None:
    inspect: dict[str, object] = {
        "Id": "def456",
        "Created": "2026-01-01T00:00:00Z",
        "State": {
            "Status": "exited",
            "StartedAt": "2026-01-01T00:01:00Z",
        },
        "Config": {"Image": "test-image"},
        "NetworkSettings": {"IPAddress": ""},
    }
    info = build_container_info(inspect, None, None, "pd-stopped")
    assert info.status == "exited"
    assert info.uptime is None  # not running → no uptime
    assert info.memory_usage == ""
    assert info.network is False


def test_build_container_info_zero_started_at() -> None:
    inspect: dict[str, object] = {
        "Id": "ghi789",
        "Created": "2026-01-01T00:00:00Z",
        "State": {
            "Status": "created",
            "StartedAt": "0001-01-01T00:00:00Z",
        },
        "Config": {"Image": "img"},
        "NetworkSettings": {},
    }
    info = build_container_info(inspect, None, None, "pd-new")
    assert info.started_at is None


def test_build_container_info_missing_state() -> None:
    inspect: dict[str, object] = {
        "Id": "x",
        "Created": "2026-01-01T00:00:00Z",
    }
    info = build_container_info(inspect, None, None, "pd-x")
    assert info.status == "unknown"


# --- build_exposed_ports ---


def test_build_exposed_ports_single() -> None:
    result = build_exposed_ports({8080: 80})
    assert result == {"80/tcp": {}}


def test_build_exposed_ports_multiple() -> None:
    result = build_exposed_ports({8080: 80, 3000: 3000})
    assert result == {"80/tcp": {}, "3000/tcp": {}}


def test_build_exposed_ports_empty() -> None:
    assert build_exposed_ports({}) == {}


# --- build_port_bindings ---


def test_build_port_bindings_single() -> None:
    result = build_port_bindings({8080: 80})
    assert result == {"80/tcp": [{"HostPort": "8080"}]}


def test_build_port_bindings_multiple() -> None:
    result = build_port_bindings({8080: 80, 3000: 3000})
    assert result == {
        "80/tcp": [{"HostPort": "8080"}],
        "3000/tcp": [{"HostPort": "3000"}],
    }


def test_build_port_bindings_empty() -> None:
    assert build_port_bindings({}) == {}


# --- parse_port_bindings ---


def test_parse_port_bindings_normal() -> None:
    inspect: dict[str, object] = {
        "HostConfig": {
            "PortBindings": {
                "80/tcp": [{"HostPort": "8080"}],
            }
        }
    }
    assert parse_port_bindings(inspect) == {8080: 80}


def test_parse_port_bindings_multiple() -> None:
    inspect: dict[str, object] = {
        "HostConfig": {
            "PortBindings": {
                "80/tcp": [{"HostPort": "8080"}],
                "3000/tcp": [{"HostPort": "3000"}],
            }
        }
    }
    result = parse_port_bindings(inspect)
    assert result == {8080: 80, 3000: 3000}


def test_parse_port_bindings_empty() -> None:
    assert parse_port_bindings({}) == {}


def test_parse_port_bindings_no_host_config() -> None:
    assert parse_port_bindings({"HostConfig": {}}) == {}


def test_parse_port_bindings_none_bindings() -> None:
    inspect: dict[str, object] = {"HostConfig": {"PortBindings": None}}
    assert parse_port_bindings(inspect) == {}


def test_parse_port_bindings_non_list_binding() -> None:
    inspect: dict[str, object] = {"HostConfig": {"PortBindings": {"80/tcp": "bad"}}}
    assert parse_port_bindings(inspect) == {}


def test_parse_port_bindings_non_dict_entry() -> None:
    inspect: dict[str, object] = {"HostConfig": {"PortBindings": {"80/tcp": ["not_a_dict"]}}}
    assert parse_port_bindings(inspect) == {}


def test_parse_port_bindings_missing_host_port() -> None:
    inspect: dict[str, object] = {"HostConfig": {"PortBindings": {"80/tcp": [{}]}}}
    assert parse_port_bindings(inspect) == {}


# --- build_container_info with ports ---


def test_build_container_info_with_ports() -> None:
    inspect: dict[str, object] = {
        "Id": "abc123",
        "Created": "2026-01-01T00:00:00Z",
        "State": {"Status": "running"},
        "Config": {"Image": "test"},
        "NetworkSettings": {"IPAddress": ""},
        "HostConfig": {
            "PortBindings": {
                "80/tcp": [{"HostPort": "8080"}],
            }
        },
    }
    info = build_container_info(inspect, None, None, "pd-ports")
    assert info.ports == {8080: 80}
