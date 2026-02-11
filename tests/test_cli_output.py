"""Tests for CLI output formatters."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

from pocket_dock.cli._output import (
    click_echo_json,
    confirm_destructive,
    format_container_info,
    format_container_list,
    format_doctor_report,
    format_error,
    format_exec_result,
    print_success,
)
from pocket_dock.errors import (
    ContainerNotFound,
    ImageNotFound,
    PodmanNotRunning,
    ProjectNotInitialized,
    SocketCommunicationError,
)
from pocket_dock.types import ContainerInfo, ContainerListItem, DoctorReport, ExecResult

# --- format_container_list ---


def test_format_container_list_json() -> None:
    items = [
        ContainerListItem(
            id="abc123def456",
            name="test-1",
            status="running",
            image="alpine:latest",
            created_at="2024-01-01T00:00:00",
            persist=True,
            project="myproj",
        )
    ]
    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        format_container_list(items, json_output=True)
        output = mock_stdout.getvalue()
    data = json.loads(output)
    assert len(data) == 1
    assert data[0]["name"] == "test-1"
    assert data[0]["persist"] is True


def test_format_container_list_empty() -> None:
    # Should print "No containers found." — just ensure no exception
    format_container_list([], json_output=False)


def test_format_container_list_table() -> None:
    items = [
        ContainerListItem(
            id="abc123",
            name="c1",
            status="running",
            image="alpine",
            created_at="2024-01-01",
            persist=False,
            project="proj",
        ),
        ContainerListItem(
            id="def456",
            name="c2",
            status="exited",
            image="ubuntu",
            created_at="2024-01-02",
            persist=True,
            project="proj",
        ),
    ]
    # Should render a Rich table without error
    format_container_list(items, json_output=False)


# --- format_container_info ---


def _make_info() -> ContainerInfo:
    import datetime

    return ContainerInfo(
        id="abc123def456789",
        name="test-container",
        status="running",
        image="alpine:latest",
        created_at=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc),
        memory_usage="50MB",
        memory_limit="256MB",
        cpu_percent=25.0,
        pids=5,
        ip_address="10.0.0.2",
    )


def test_format_container_info_json() -> None:
    info = _make_info()
    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        format_container_info(info, json_output=True)
        output = mock_stdout.getvalue()
    data = json.loads(output)
    assert data["name"] == "test-container"
    assert data["status"] == "running"


def test_format_container_info_panel() -> None:
    info = _make_info()
    format_container_info(info, json_output=False)


def test_format_container_info_minimal() -> None:
    import datetime

    info = ContainerInfo(
        id="abc123",
        name="minimal",
        status="exited",
        image="alpine",
        created_at=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc),
    )
    format_container_info(info, json_output=False)


# --- format_exec_result ---


def test_format_exec_result_stdout() -> None:
    result = ExecResult(exit_code=0, stdout="hello world")
    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        format_exec_result(result)
        assert "hello world" in mock_stdout.getvalue()


def test_format_exec_result_stderr() -> None:
    result = ExecResult(exit_code=1, stderr="error msg")
    with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
        format_exec_result(result)
        assert "error msg" in mock_stderr.getvalue()


def test_format_exec_result_with_newlines() -> None:
    result = ExecResult(exit_code=0, stdout="hello\n", stderr="err\n")
    with (
        patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        patch("sys.stderr", new_callable=StringIO) as mock_stderr,
    ):
        format_exec_result(result)
        assert mock_stdout.getvalue() == "hello\n"
        assert mock_stderr.getvalue() == "err\n"


def test_format_exec_result_empty() -> None:
    result = ExecResult(exit_code=0)
    with (
        patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        patch("sys.stderr", new_callable=StringIO) as mock_stderr,
    ):
        format_exec_result(result)
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue() == ""


# --- format_doctor_report ---


def test_format_doctor_report_json() -> None:
    report = DoctorReport(
        orphaned_containers=("orphan-1",),
        stale_instance_dirs=("stale-1",),
        healthy=2,
    )
    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        format_doctor_report(report, json_output=True)
        output = mock_stdout.getvalue()
    data = json.loads(output)
    assert data["healthy"] == 2
    assert "orphan-1" in data["orphaned_containers"]


def test_format_doctor_report_panel_healthy() -> None:
    report = DoctorReport(orphaned_containers=(), stale_instance_dirs=(), healthy=3)
    format_doctor_report(report, json_output=False)


def test_format_doctor_report_panel_issues() -> None:
    report = DoctorReport(
        orphaned_containers=("o1", "o2"),
        stale_instance_dirs=("s1",),
        healthy=0,
    )
    format_doctor_report(report, json_output=False)


def test_format_doctor_report_nothing() -> None:
    report = DoctorReport(orphaned_containers=(), stale_instance_dirs=(), healthy=0)
    format_doctor_report(report, json_output=False)


# --- format_error ---


def test_format_error_podman_not_running() -> None:
    err = PodmanNotRunning()
    format_error(err)


def test_format_error_container_not_found() -> None:
    err = ContainerNotFound("my-container")
    format_error(err)


def test_format_error_image_not_found() -> None:
    err = ImageNotFound("missing:latest")
    format_error(err)


def test_format_error_project_not_initialized() -> None:
    err = ProjectNotInitialized()
    format_error(err)


def test_format_error_generic() -> None:
    err = SocketCommunicationError("something broke")
    format_error(err)


# --- print_success ---


def test_print_success() -> None:
    print_success("Done!")


# --- confirm_destructive ---


def test_confirm_destructive_yes() -> None:
    with patch.object(
        __import__("pocket_dock.cli._output", fromlist=["_console"]),
        "_console",
    ) as mock_console:
        mock_console.input.return_value = "y"
        result = confirm_destructive("Are you sure?")
    assert result is True


def test_confirm_destructive_no() -> None:
    with patch.object(
        __import__("pocket_dock.cli._output", fromlist=["_console"]),
        "_console",
    ) as mock_console:
        mock_console.input.return_value = "n"
        result = confirm_destructive("Are you sure?")
    assert result is False


# --- click_echo_json ---


def test_click_echo_json() -> None:
    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        click_echo_json({"key": "value"})
        data = json.loads(mock_stdout.getvalue())
    assert data["key"] == "value"
