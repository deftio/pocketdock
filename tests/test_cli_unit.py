"""Unit tests for the CLI using Click's CliRunner with mocked SDK."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner
from pocketdock.cli.main import CliContext, cli
from pocketdock.errors import ContainerNotFound, PodmanNotRunning, ProjectNotInitialized
from pocketdock.types import ContainerInfo, ContainerListItem, DoctorReport

# --- Scaffold tests ---


def test_cli_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "pocketdock" in result.output.lower() or "Usage" in result.output


def test_cli_version() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "1.1.1" in result.output


def test_cli_socket_option() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--socket", "/tmp/test.sock", "--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output


def test_cli_verbose_option() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--verbose", "--help"])
    assert result.exit_code == 0


def test_cli_context_defaults() -> None:
    ctx = CliContext()
    assert ctx.socket is None
    assert ctx.verbose is False
    assert ctx.json_output is False


# --- init command ---


def test_init_success(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "myproject"
    target.mkdir()
    result = runner.invoke(cli, ["init", str(target)])
    assert result.exit_code == 0
    assert "initialized" in result.output.lower() or "\u2713" in result.output


def test_init_with_name(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "proj2"
    target.mkdir()
    result = runner.invoke(cli, ["init", "--name", "custom-name", str(target)])
    assert result.exit_code == 0


def test_init_default_cwd(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0


@patch("pocketdock.init_project")
def test_init_error(mock_init: MagicMock) -> None:
    mock_init.side_effect = PodmanNotRunning()
    runner = CliRunner()
    result = runner.invoke(cli, ["init"])
    assert result.exit_code == 1


def test_init_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--help"])
    assert result.exit_code == 0
    assert "Initialize" in result.output


# --- list command ---


@patch("pocketdock.list_containers")
def test_list_empty(mock_list: MagicMock) -> None:
    mock_list.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["list"])
    assert result.exit_code == 0


@patch("pocketdock.list_containers")
def test_list_with_containers(mock_list: MagicMock) -> None:
    mock_list.return_value = [
        ContainerListItem(
            id="abc123",
            name="test-1",
            status="running",
            image="alpine:latest",
            created_at="2024-01-01",
            persist=True,
            project="proj",
        )
    ]
    runner = CliRunner()
    result = runner.invoke(cli, ["list"])
    assert result.exit_code == 0


@patch("pocketdock.list_containers")
def test_list_json(mock_list: MagicMock) -> None:
    mock_list.return_value = [
        ContainerListItem(
            id="abc123",
            name="test-1",
            status="running",
            image="alpine:latest",
            created_at="2024-01-01",
            persist=False,
            project="proj",
        )
    ]
    runner = CliRunner()
    result = runner.invoke(cli, ["list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["name"] == "test-1"


@patch("pocketdock.list_containers")
def test_list_with_project_filter(mock_list: MagicMock) -> None:
    mock_list.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["list", "--project", "myproj"])
    assert result.exit_code == 0
    mock_list.assert_called_once_with(socket_path=None, project="myproj")


@patch("pocketdock.list_containers")
def test_list_with_socket(mock_list: MagicMock) -> None:
    mock_list.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["--socket", "/tmp/test.sock", "list"])
    assert result.exit_code == 0
    mock_list.assert_called_once_with(socket_path="/tmp/test.sock", project=None)


@patch("pocketdock.list_containers")
def test_list_engine_error(mock_list: MagicMock) -> None:
    mock_list.side_effect = PodmanNotRunning()
    runner = CliRunner()
    result = runner.invoke(cli, ["list"])
    assert result.exit_code == 1


def test_list_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["list", "--help"])
    assert result.exit_code == 0


# --- info command ---


def _make_container_mock() -> MagicMock:
    container = MagicMock()
    container.info.return_value = ContainerInfo(
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
    return container


@patch("pocketdock.resume_container")
def test_info_success(mock_resume: MagicMock) -> None:
    mock_resume.return_value = _make_container_mock()
    runner = CliRunner()
    result = runner.invoke(cli, ["info", "test-container"])
    assert result.exit_code == 0


@patch("pocketdock.resume_container")
def test_info_json(mock_resume: MagicMock) -> None:
    mock_resume.return_value = _make_container_mock()
    runner = CliRunner()
    result = runner.invoke(cli, ["info", "test-container", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["name"] == "test-container"


@patch("pocketdock.resume_container")
def test_info_not_found(mock_resume: MagicMock) -> None:
    mock_resume.side_effect = ContainerNotFound("missing")
    runner = CliRunner()
    result = runner.invoke(cli, ["info", "missing"])
    assert result.exit_code == 1


@patch("pocketdock.resume_container")
def test_info_runtime_error(mock_resume: MagicMock) -> None:
    container = MagicMock()
    container.info.side_effect = RuntimeError("boom")
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["info", "test"])
    assert result.exit_code == 1


@patch("pocketdock.resume_container")
def test_info_pocketdock_error(mock_resume: MagicMock) -> None:
    from pocketdock.errors import ContainerGone

    container = MagicMock()
    container.info.side_effect = ContainerGone("abc123")
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["info", "test"])
    assert result.exit_code == 1


def test_info_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["info", "--help"])
    assert result.exit_code == 0


# --- doctor command ---


@patch("pocketdock.doctor")
def test_doctor_healthy(mock_doctor: MagicMock) -> None:
    mock_doctor.return_value = DoctorReport(
        orphaned_containers=(), stale_instance_dirs=(), healthy=3
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor"])
    assert result.exit_code == 0


@patch("pocketdock.doctor")
def test_doctor_json(mock_doctor: MagicMock) -> None:
    mock_doctor.return_value = DoctorReport(
        orphaned_containers=("orphan",), stale_instance_dirs=(), healthy=1
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["healthy"] == 1


@patch("pocketdock.doctor")
def test_doctor_not_initialized(mock_doctor: MagicMock) -> None:
    mock_doctor.side_effect = ProjectNotInitialized()
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor"])
    assert result.exit_code == 1


@patch("pocketdock.doctor")
def test_doctor_engine_error(mock_doctor: MagicMock) -> None:
    mock_doctor.side_effect = PodmanNotRunning()
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor"])
    assert result.exit_code == 1


def test_doctor_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor", "--help"])
    assert result.exit_code == 0


# --- status command ---


@patch("pocketdock.list_containers")
@patch("pocketdock.projects.list_instance_dirs")
@patch("pocketdock.projects.get_project_name")
@patch("pocketdock.find_project_root")
def test_status_success(
    mock_root: MagicMock,
    mock_name: MagicMock,
    mock_dirs: MagicMock,
    mock_list: MagicMock,
) -> None:
    mock_root.return_value = Path("/proj")
    mock_name.return_value = "myproject"
    mock_dirs.return_value = [Path("/proj/.pocketdock/instances/inst1")]
    mock_list.return_value = [
        ContainerListItem(
            id="abc",
            name="inst1",
            status="running",
            image="alpine",
            created_at="2024-01-01",
            persist=False,
        )
    ]
    runner = CliRunner()
    result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0


@patch("pocketdock.list_containers")
@patch("pocketdock.projects.list_instance_dirs")
@patch("pocketdock.projects.get_project_name")
@patch("pocketdock.find_project_root")
def test_status_json(
    mock_root: MagicMock,
    mock_name: MagicMock,
    mock_dirs: MagicMock,
    mock_list: MagicMock,
) -> None:
    mock_root.return_value = Path("/proj")
    mock_name.return_value = "myproject"
    mock_dirs.return_value = []
    mock_list.return_value = [
        ContainerListItem(
            id="a",
            name="c1",
            status="running",
            image="alpine",
            created_at="",
            persist=False,
        ),
        ContainerListItem(
            id="b",
            name="c2",
            status="exited",
            image="alpine",
            created_at="",
            persist=False,
        ),
    ]
    runner = CliRunner()
    result = runner.invoke(cli, ["status", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["project"] == "myproject"
    assert data["running"] == 1
    assert data["stopped"] == 1


@patch("pocketdock.find_project_root")
def test_status_no_project(mock_root: MagicMock) -> None:
    mock_root.return_value = None
    runner = CliRunner()
    result = runner.invoke(cli, ["status"])
    assert result.exit_code == 1


@patch("pocketdock.list_containers")
@patch("pocketdock.projects.list_instance_dirs")
@patch("pocketdock.projects.get_project_name")
@patch("pocketdock.find_project_root")
def test_status_engine_error(
    mock_root: MagicMock,
    mock_name: MagicMock,
    mock_dirs: MagicMock,
    mock_list: MagicMock,
) -> None:
    mock_root.return_value = Path("/proj")
    mock_name.return_value = "proj"
    mock_dirs.return_value = []
    mock_list.side_effect = PodmanNotRunning()
    runner = CliRunner()
    result = runner.invoke(cli, ["status"])
    assert result.exit_code == 1


def test_status_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["status", "--help"])
    assert result.exit_code == 0


# --- logs command ---


@patch("pocketdock.projects.list_instance_dirs")
@patch("pocketdock.find_project_root")
def test_logs_success(mock_root: MagicMock, mock_dirs: MagicMock, tmp_path: Path) -> None:
    mock_root.return_value = tmp_path
    inst = tmp_path / ".pocketdock" / "instances" / "inst1"
    logs_dir = inst / "logs"
    logs_dir.mkdir(parents=True)
    history = logs_dir / "history.jsonl"
    history.write_text(
        json.dumps({"type": "run", "command": "echo hi", "exit_code": 0, "duration_ms": 10.0})
        + "\n"
    )
    mock_dirs.return_value = [inst]
    runner = CliRunner()
    result = runner.invoke(cli, ["logs"])
    assert result.exit_code == 0


@patch("pocketdock.projects.list_instance_dirs")
@patch("pocketdock.find_project_root")
def test_logs_json(mock_root: MagicMock, mock_dirs: MagicMock, tmp_path: Path) -> None:
    mock_root.return_value = tmp_path
    inst = tmp_path / ".pocketdock" / "instances" / "inst1"
    logs_dir = inst / "logs"
    logs_dir.mkdir(parents=True)
    history = logs_dir / "history.jsonl"
    history.write_text(
        json.dumps({"type": "run", "command": "ls", "exit_code": 0, "duration_ms": 5.0}) + "\n"
    )
    mock_dirs.return_value = [inst]
    runner = CliRunner()
    result = runner.invoke(cli, ["logs", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1


@patch("pocketdock.projects.list_instance_dirs")
@patch("pocketdock.find_project_root")
def test_logs_filter_by_container(
    mock_root: MagicMock, mock_dirs: MagicMock, tmp_path: Path
) -> None:
    mock_root.return_value = tmp_path
    inst1 = tmp_path / ".pocketdock" / "instances" / "inst1"
    inst2 = tmp_path / ".pocketdock" / "instances" / "inst2"
    for inst in [inst1, inst2]:
        logs_dir = inst / "logs"
        logs_dir.mkdir(parents=True)
    (inst1 / "logs" / "history.jsonl").write_text(
        json.dumps({"type": "run", "command": "echo 1"}) + "\n"
    )
    (inst2 / "logs" / "history.jsonl").write_text(
        json.dumps({"type": "run", "command": "echo 2"}) + "\n"
    )
    mock_dirs.return_value = [inst1, inst2]
    runner = CliRunner()
    result = runner.invoke(cli, ["logs", "inst1", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["command"] == "echo 1"


@patch("pocketdock.projects.list_instance_dirs")
@patch("pocketdock.find_project_root")
def test_logs_filter_by_type(mock_root: MagicMock, mock_dirs: MagicMock, tmp_path: Path) -> None:
    mock_root.return_value = tmp_path
    inst = tmp_path / ".pocketdock" / "instances" / "inst1"
    logs_dir = inst / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "history.jsonl").write_text(
        json.dumps({"type": "run", "command": "echo 1"})
        + "\n"
        + json.dumps({"type": "session", "command": "bash"})
        + "\n"
    )
    mock_dirs.return_value = [inst]
    runner = CliRunner()
    result = runner.invoke(cli, ["logs", "--type", "session", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["type"] == "session"


@patch("pocketdock.projects.list_instance_dirs")
@patch("pocketdock.find_project_root")
def test_logs_last_n(mock_root: MagicMock, mock_dirs: MagicMock, tmp_path: Path) -> None:
    mock_root.return_value = tmp_path
    inst = tmp_path / ".pocketdock" / "instances" / "inst1"
    logs_dir = inst / "logs"
    logs_dir.mkdir(parents=True)
    lines = "\n".join(json.dumps({"type": "run", "command": f"cmd{i}"}) for i in range(20))
    (logs_dir / "history.jsonl").write_text(lines + "\n")
    mock_dirs.return_value = [inst]
    runner = CliRunner()
    result = runner.invoke(cli, ["logs", "--last", "3", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 3
    assert data[0]["command"] == "cmd17"


@patch("pocketdock.find_project_root")
def test_logs_no_project(mock_root: MagicMock) -> None:
    mock_root.return_value = None
    runner = CliRunner()
    result = runner.invoke(cli, ["logs"])
    assert result.exit_code == 1


@patch("pocketdock.projects.list_instance_dirs")
@patch("pocketdock.find_project_root")
def test_logs_container_not_found(mock_root: MagicMock, mock_dirs: MagicMock) -> None:
    mock_root.return_value = Path("/proj")
    mock_dirs.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["logs", "nonexistent"])
    assert result.exit_code == 1


@patch("pocketdock.projects.list_instance_dirs")
@patch("pocketdock.find_project_root")
def test_logs_empty(mock_root: MagicMock, mock_dirs: MagicMock) -> None:
    mock_root.return_value = Path("/proj")
    mock_dirs.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["logs"])
    assert result.exit_code == 0
    assert "No log entries found" in result.output


@patch("pocketdock.projects.list_instance_dirs")
@patch("pocketdock.find_project_root")
def test_logs_invalid_json_skipped(
    mock_root: MagicMock, mock_dirs: MagicMock, tmp_path: Path
) -> None:
    mock_root.return_value = tmp_path
    inst = tmp_path / ".pocketdock" / "instances" / "inst1"
    logs_dir = inst / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "history.jsonl").write_text("not json\n{bad\n\n")
    mock_dirs.return_value = [inst]
    runner = CliRunner()
    result = runner.invoke(cli, ["logs", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == []


@patch("pocketdock.projects.list_instance_dirs")
@patch("pocketdock.find_project_root")
def test_logs_table_with_error_exit(
    mock_root: MagicMock, mock_dirs: MagicMock, tmp_path: Path
) -> None:
    mock_root.return_value = tmp_path
    inst = tmp_path / ".pocketdock" / "instances" / "inst1"
    logs_dir = inst / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "history.jsonl").write_text(
        json.dumps({"type": "run", "command": "fail", "exit_code": 1, "duration_ms": 100.0}) + "\n"
    )
    mock_dirs.return_value = [inst]
    runner = CliRunner()
    result = runner.invoke(cli, ["logs"])
    assert result.exit_code == 0


@patch("pocketdock.projects.list_instance_dirs")
@patch("pocketdock.find_project_root")
def test_logs_table_no_exit_code(
    mock_root: MagicMock, mock_dirs: MagicMock, tmp_path: Path
) -> None:
    mock_root.return_value = tmp_path
    inst = tmp_path / ".pocketdock" / "instances" / "inst1"
    logs_dir = inst / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "history.jsonl").write_text(
        json.dumps({"type": "session", "command": "bash", "timestamp": "2024-01-01T00:00:00"})
        + "\n"
    )
    mock_dirs.return_value = [inst]
    runner = CliRunner()
    result = runner.invoke(cli, ["logs"])
    assert result.exit_code == 0


@patch("pocketdock.projects.list_instance_dirs")
@patch("pocketdock.find_project_root")
def test_logs_no_history_file(mock_root: MagicMock, mock_dirs: MagicMock, tmp_path: Path) -> None:
    mock_root.return_value = tmp_path
    inst = tmp_path / ".pocketdock" / "instances" / "inst1"
    inst.mkdir(parents=True)
    # No logs/history.jsonl file created
    mock_dirs.return_value = [inst]
    runner = CliRunner()
    result = runner.invoke(cli, ["logs", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == []


def test_logs_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["logs", "--help"])
    assert result.exit_code == 0


# --- create command ---


@patch("pocketdock.create_new_container")
def test_create_success(mock_create: MagicMock) -> None:
    container = MagicMock()
    container.name = "test-c"
    container.container_id = "abc123def456"
    mock_create.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["create"])
    assert result.exit_code == 0


@patch("pocketdock.create_new_container")
def test_create_with_options(mock_create: MagicMock) -> None:
    container = MagicMock()
    container.name = "custom"
    container.container_id = "abc123def456"
    mock_create.return_value = container
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "create",
            "--image",
            "ubuntu:latest",
            "--name",
            "custom",
            "--timeout",
            "60",
            "--mem-limit",
            "512m",
            "--cpu-percent",
            "50",
            "--persist",
            "--project",
            "myproj",
            "-v",
            "/host:/container",
        ],
    )
    assert result.exit_code == 0
    call_kwargs = mock_create.call_args[1]
    assert call_kwargs["image"] == "ubuntu:latest"
    assert call_kwargs["name"] == "custom"
    assert call_kwargs["timeout"] == 60
    assert call_kwargs["mem_limit"] == "512m"
    assert call_kwargs["cpu_percent"] == 50
    assert call_kwargs["persist"] is True
    assert call_kwargs["project"] == "myproj"
    assert call_kwargs["volumes"] == {"/host": "/container"}


@patch("pocketdock.create_new_container")
def test_create_with_socket(mock_create: MagicMock) -> None:
    container = MagicMock()
    container.name = "test"
    container.container_id = "abc123"
    mock_create.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["--socket", "/tmp/test.sock", "create"])
    assert result.exit_code == 0


@patch("pocketdock.create_new_container")
def test_create_error(mock_create: MagicMock) -> None:
    mock_create.side_effect = PodmanNotRunning()
    runner = CliRunner()
    result = runner.invoke(cli, ["create"])
    assert result.exit_code == 1


@patch("pocketdock.create_new_container")
def test_create_volume_invalid_format(mock_create: MagicMock) -> None:
    container = MagicMock()
    container.name = "test"
    container.container_id = "abc123"
    mock_create.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "-v", "no-colon"])
    assert result.exit_code == 0
    # No volumes should be passed since format is invalid
    call_kwargs = mock_create.call_args[1]
    assert "volumes" not in call_kwargs


@patch("pocketdock.create_new_container")
def test_create_restores_existing_env(mock_create: MagicMock) -> None:
    import os

    container = MagicMock()
    container.name = "test"
    container.container_id = "abc123def456"
    mock_create.return_value = container
    os.environ["POCKETDOCK_SOCKET"] = "/original/socket"
    try:
        runner = CliRunner()
        result = runner.invoke(cli, ["--socket", "/tmp/test.sock", "create"])
        assert result.exit_code == 0
        assert os.environ.get("POCKETDOCK_SOCKET") == "/original/socket"
    finally:
        os.environ.pop("POCKETDOCK_SOCKET", None)


def test_create_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "--help"])
    assert result.exit_code == 0


# --- run command ---


@patch("pocketdock.resume_container")
def test_run_success(mock_resume: MagicMock) -> None:
    container = MagicMock()
    container.run.return_value = MagicMock(exit_code=0, stdout="hello\n", stderr="")
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "myc", "echo", "hello"])
    assert result.exit_code == 0


@patch("pocketdock.resume_container")
def test_run_nonzero_exit(mock_resume: MagicMock) -> None:
    container = MagicMock()
    container.run.return_value = MagicMock(exit_code=42, stdout="", stderr="err")
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "myc", "false"])
    assert result.exit_code == 42


@patch("pocketdock.resume_container")
def test_run_with_options(mock_resume: MagicMock) -> None:
    container = MagicMock()
    container.run.return_value = MagicMock(exit_code=0, stdout="", stderr="")
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["run", "myc", "--timeout", "10", "--max-output", "1000", "--lang", "python", "cmd"],
    )
    assert result.exit_code == 0


@patch("pocketdock.resume_container")
def test_run_stream(mock_resume: MagicMock) -> None:
    from pocketdock.types import StreamChunk

    container = MagicMock()
    chunks = [StreamChunk(stream="stdout", data="line1\n"), StreamChunk(stream="stderr", data="e")]
    container.run.return_value = iter(chunks)
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "myc", "--stream", "echo", "hi"])
    assert result.exit_code == 0


@patch("pocketdock.resume_container")
def test_run_stream_with_options(mock_resume: MagicMock) -> None:
    from pocketdock.types import StreamChunk

    container = MagicMock()
    container.run.return_value = iter([StreamChunk(stream="stdout", data="x")])
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "run",
            "myc",
            "--stream",
            "--timeout",
            "5",
            "--max-output",
            "100",
            "--lang",
            "bash",
            "ls",
        ],
    )
    assert result.exit_code == 0


@patch("pocketdock.resume_container")
def test_run_detach(mock_resume: MagicMock) -> None:
    container = MagicMock()
    proc = MagicMock()
    proc.id = "exec-abc123"
    container.run.return_value = proc
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "myc", "--detach", "sleep", "100"])
    assert result.exit_code == 0


@patch("pocketdock.resume_container")
def test_run_detach_with_options(mock_resume: MagicMock) -> None:
    container = MagicMock()
    proc = MagicMock()
    proc.id = "exec-xyz"
    container.run.return_value = proc
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "run",
            "myc",
            "--detach",
            "--timeout",
            "30",
            "--max-output",
            "500",
            "--lang",
            "py",
            "cmd",
        ],
    )
    assert result.exit_code == 0


@patch("pocketdock.resume_container")
def test_run_container_not_found(mock_resume: MagicMock) -> None:
    mock_resume.side_effect = ContainerNotFound("missing")
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "missing", "echo"])
    assert result.exit_code == 1


@patch("pocketdock.resume_container")
def test_run_error_in_execution(mock_resume: MagicMock) -> None:
    container = MagicMock()
    container.run.side_effect = RuntimeError("boom")
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "myc", "echo"])
    assert result.exit_code == 1


@patch("pocketdock.resume_container")
def test_run_pocketdock_error_in_execution(mock_resume: MagicMock) -> None:
    from pocketdock.errors import ContainerGone

    container = MagicMock()
    container.run.side_effect = ContainerGone("abc123")
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "myc", "echo"])
    assert result.exit_code == 1


def test_run_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--help"])
    assert result.exit_code == 0


# --- push command ---


@patch("pocketdock.resume_container")
def test_push_success(mock_resume: MagicMock) -> None:
    container = MagicMock()
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["push", "myc", "/local/file", "/container/file"])
    assert result.exit_code == 0
    container.push.assert_called_once_with("/local/file", "/container/file")


@patch("pocketdock.resume_container")
def test_push_error(mock_resume: MagicMock) -> None:
    container = MagicMock()
    container.push.side_effect = RuntimeError("fail")
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["push", "myc", "/a", "/b"])
    assert result.exit_code == 1


@patch("pocketdock.resume_container")
def test_push_pocketdock_error(mock_resume: MagicMock) -> None:
    from pocketdock.errors import ContainerGone

    container = MagicMock()
    container.push.side_effect = ContainerGone("abc")
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["push", "myc", "/a", "/b"])
    assert result.exit_code == 1


def test_push_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["push", "--help"])
    assert result.exit_code == 0


# --- pull command ---


@patch("pocketdock.resume_container")
def test_pull_success(mock_resume: MagicMock) -> None:
    container = MagicMock()
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["pull", "myc", "/container/file", "/local/file"])
    assert result.exit_code == 0
    container.pull.assert_called_once_with("/container/file", "/local/file")


@patch("pocketdock.resume_container")
def test_pull_error(mock_resume: MagicMock) -> None:
    container = MagicMock()
    container.pull.side_effect = RuntimeError("fail")
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["pull", "myc", "/a", "/b"])
    assert result.exit_code == 1


@patch("pocketdock.resume_container")
def test_pull_pocketdock_error(mock_resume: MagicMock) -> None:
    from pocketdock.errors import ContainerGone

    container = MagicMock()
    container.pull.side_effect = ContainerGone("abc")
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["pull", "myc", "/a", "/b"])
    assert result.exit_code == 1


def test_pull_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["pull", "--help"])
    assert result.exit_code == 0


# --- reboot command ---


@patch("pocketdock.resume_container")
def test_reboot_success(mock_resume: MagicMock) -> None:
    container = MagicMock()
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["reboot", "myc"])
    assert result.exit_code == 0
    container.reboot.assert_called_once_with(fresh=False)


@patch("pocketdock.resume_container")
def test_reboot_fresh(mock_resume: MagicMock) -> None:
    container = MagicMock()
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["reboot", "myc", "--fresh"])
    assert result.exit_code == 0
    container.reboot.assert_called_once_with(fresh=True)


@patch("pocketdock.resume_container")
def test_reboot_error(mock_resume: MagicMock) -> None:
    from pocketdock.errors import ContainerGone

    container = MagicMock()
    container.reboot.side_effect = ContainerGone("abc")
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["reboot", "myc"])
    assert result.exit_code == 1


@patch("pocketdock.resume_container")
def test_reboot_runtime_error(mock_resume: MagicMock) -> None:
    container = MagicMock()
    container.reboot.side_effect = RuntimeError("boom")
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["reboot", "myc"])
    assert result.exit_code == 1


def test_reboot_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["reboot", "--help"])
    assert result.exit_code == 0


# --- stop command ---


@patch("pocketdock.stop_container")
def test_stop_success(mock_stop: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["stop", "myc"])
    assert result.exit_code == 0
    mock_stop.assert_called_once_with("myc", socket_path=None)


@patch("pocketdock.stop_container")
def test_stop_with_socket(mock_stop: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--socket", "/tmp/s.sock", "stop", "myc"])
    assert result.exit_code == 0
    mock_stop.assert_called_once_with("myc", socket_path="/tmp/s.sock")


@patch("pocketdock.stop_container")
def test_stop_not_found(mock_stop: MagicMock) -> None:
    mock_stop.side_effect = ContainerNotFound("missing")
    runner = CliRunner()
    result = runner.invoke(cli, ["stop", "missing"])
    assert result.exit_code == 1


def test_stop_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["stop", "--help"])
    assert result.exit_code == 0


# --- resume command ---


@patch("pocketdock.resume_container")
def test_resume_success(mock_resume: MagicMock) -> None:
    container = MagicMock()
    container.container_id = "abc123def456"
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["resume", "myc"])
    assert result.exit_code == 0


@patch("pocketdock.resume_container")
def test_resume_not_found(mock_resume: MagicMock) -> None:
    mock_resume.side_effect = ContainerNotFound("missing")
    runner = CliRunner()
    result = runner.invoke(cli, ["resume", "missing"])
    assert result.exit_code == 1


def test_resume_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["resume", "--help"])
    assert result.exit_code == 0


# --- shutdown command ---


@patch("pocketdock.destroy_container")
def test_shutdown_with_yes(mock_destroy: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["shutdown", "myc", "--yes"])
    assert result.exit_code == 0
    mock_destroy.assert_called_once_with("myc", socket_path=None)


@patch("pocketdock.cli._output.confirm_destructive")
@patch("pocketdock.destroy_container")
def test_shutdown_confirmed(mock_destroy: MagicMock, mock_confirm: MagicMock) -> None:
    mock_confirm.return_value = True
    runner = CliRunner()
    result = runner.invoke(cli, ["shutdown", "myc"])
    assert result.exit_code == 0
    mock_destroy.assert_called_once()


@patch("pocketdock.cli._output.confirm_destructive")
def test_shutdown_aborted(mock_confirm: MagicMock) -> None:
    mock_confirm.return_value = False
    runner = CliRunner()
    result = runner.invoke(cli, ["shutdown", "myc"])
    assert result.exit_code == 0
    assert "Aborted" in result.output


@patch("pocketdock.destroy_container")
def test_shutdown_error(mock_destroy: MagicMock) -> None:
    mock_destroy.side_effect = ContainerNotFound("missing")
    runner = CliRunner()
    result = runner.invoke(cli, ["shutdown", "missing", "--yes"])
    assert result.exit_code == 1


def test_shutdown_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["shutdown", "--help"])
    assert result.exit_code == 0


# --- snapshot command ---


@patch("pocketdock.resume_container")
def test_snapshot_success(mock_resume: MagicMock) -> None:
    container = MagicMock()
    container.snapshot.return_value = "sha256:abc123def456"
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["snapshot", "myc", "my-image:v1"])
    assert result.exit_code == 0


@patch("pocketdock.resume_container")
def test_snapshot_error(mock_resume: MagicMock) -> None:
    container = MagicMock()
    container.snapshot.side_effect = RuntimeError("fail")
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["snapshot", "myc", "my-image"])
    assert result.exit_code == 1


@patch("pocketdock.resume_container")
def test_snapshot_pocketdock_error(mock_resume: MagicMock) -> None:
    from pocketdock.errors import ContainerGone

    container = MagicMock()
    container.snapshot.side_effect = ContainerGone("abc")
    mock_resume.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["snapshot", "myc", "img"])
    assert result.exit_code == 1


def test_snapshot_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["snapshot", "--help"])
    assert result.exit_code == 0


# --- prune command ---


@patch("pocketdock.prune")
def test_prune_with_yes(mock_prune: MagicMock) -> None:
    mock_prune.return_value = 3
    runner = CliRunner()
    result = runner.invoke(cli, ["prune", "--yes"])
    assert result.exit_code == 0
    assert "3" in result.output


@patch("pocketdock.prune")
def test_prune_with_project(mock_prune: MagicMock) -> None:
    mock_prune.return_value = 1
    runner = CliRunner()
    result = runner.invoke(cli, ["prune", "--yes", "--project", "myproj"])
    assert result.exit_code == 0
    mock_prune.assert_called_once_with(socket_path=None, project="myproj")


@patch("pocketdock.cli._output.confirm_destructive")
@patch("pocketdock.prune")
def test_prune_confirmed(mock_prune: MagicMock, mock_confirm: MagicMock) -> None:
    mock_confirm.return_value = True
    mock_prune.return_value = 2
    runner = CliRunner()
    result = runner.invoke(cli, ["prune"])
    assert result.exit_code == 0


@patch("pocketdock.cli._output.confirm_destructive")
def test_prune_aborted(mock_confirm: MagicMock) -> None:
    mock_confirm.return_value = False
    runner = CliRunner()
    result = runner.invoke(cli, ["prune"])
    assert result.exit_code == 0
    assert "Aborted" in result.output


@patch("pocketdock.prune")
def test_prune_error(mock_prune: MagicMock) -> None:
    mock_prune.side_effect = PodmanNotRunning()
    runner = CliRunner()
    result = runner.invoke(cli, ["prune", "--yes"])
    assert result.exit_code == 1


def test_prune_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["prune", "--help"])
    assert result.exit_code == 0


# --- shell command ---


@patch("subprocess.run")
@patch("pocketdock.resume_container")
def test_shell_success(mock_resume: MagicMock, mock_run: MagicMock) -> None:
    container = MagicMock()
    container.container_id = "abc123"
    mock_resume.return_value = container
    mock_run.return_value = MagicMock(returncode=0)
    runner = CliRunner()
    result = runner.invoke(cli, ["shell", "myc"])
    assert result.exit_code == 0
    call_args = mock_run.call_args
    assert "/bin/bash" in call_args[0][0]


@patch("subprocess.run")
@patch("pocketdock.resume_container")
def test_shell_fallback_to_sh(mock_resume: MagicMock, mock_run: MagicMock) -> None:
    container = MagicMock()
    container.container_id = "abc123"
    mock_resume.return_value = container
    mock_run.side_effect = [
        MagicMock(returncode=126),
        MagicMock(returncode=0),
    ]
    runner = CliRunner()
    result = runner.invoke(cli, ["shell", "myc"])
    assert result.exit_code == 0
    assert mock_run.call_count == 2
    second_call = mock_run.call_args_list[1]
    assert "/bin/sh" in second_call[0][0]


@patch("pocketdock.resume_container")
def test_shell_not_found(mock_resume: MagicMock) -> None:
    mock_resume.side_effect = ContainerNotFound("missing")
    runner = CliRunner()
    result = runner.invoke(cli, ["shell", "missing"])
    assert result.exit_code == 1


def test_shell_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["shell", "--help"])
    assert result.exit_code == 0


# --- _detect_engine_cli ---


def test_detect_engine_cli_podman_socket() -> None:
    from pocketdock.cli._commands import _detect_engine_cli

    assert _detect_engine_cli("/run/podman/podman.sock") == "podman"


def test_detect_engine_cli_docker_socket() -> None:
    from pocketdock.cli._commands import _detect_engine_cli

    assert _detect_engine_cli("/var/run/docker.sock") == "docker"


@patch("shutil.which")
def test_detect_engine_cli_no_socket_podman_available(mock_which: MagicMock) -> None:
    from pocketdock.cli._commands import _detect_engine_cli

    mock_which.return_value = "/usr/bin/podman"
    assert _detect_engine_cli(None) == "podman"


@patch("shutil.which")
def test_detect_engine_cli_no_socket_fallback_docker(mock_which: MagicMock) -> None:
    from pocketdock.cli._commands import _detect_engine_cli

    mock_which.return_value = None
    assert _detect_engine_cli(None) == "docker"


# --- create command with --profile and --device ---


@patch("pocketdock.create_new_container")
def test_create_with_profile(mock_create: MagicMock) -> None:
    container = MagicMock()
    container.name = "test"
    container.container_id = "abc123def456"
    mock_create.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "--profile", "dev"])
    assert result.exit_code == 0
    call_kwargs = mock_create.call_args[1]
    assert call_kwargs["profile"] == "dev"


@patch("pocketdock.create_new_container")
def test_create_with_device(mock_create: MagicMock) -> None:
    container = MagicMock()
    container.name = "test"
    container.container_id = "abc123def456"
    mock_create.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "-d", "/dev/ttyUSB0"])
    assert result.exit_code == 0
    call_kwargs = mock_create.call_args[1]
    assert call_kwargs["devices"] == ["/dev/ttyUSB0"]


@patch("pocketdock.create_new_container")
def test_create_with_multiple_devices(mock_create: MagicMock) -> None:
    container = MagicMock()
    container.name = "test"
    container.container_id = "abc123def456"
    mock_create.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "-d", "/dev/ttyUSB0", "-d", "/dev/ttyACM0"])
    assert result.exit_code == 0
    call_kwargs = mock_create.call_args[1]
    assert call_kwargs["devices"] == ["/dev/ttyUSB0", "/dev/ttyACM0"]


@patch("pocketdock.create_new_container")
def test_create_profile_and_image(mock_create: MagicMock) -> None:
    container = MagicMock()
    container.name = "test"
    container.container_id = "abc123"
    mock_create.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "--profile", "agent", "--image", "custom:latest"])
    assert result.exit_code == 0
    call_kwargs = mock_create.call_args[1]
    assert call_kwargs["image"] == "custom:latest"
    assert call_kwargs["profile"] == "agent"


# --- create command with --port ---


@patch("pocketdock.create_new_container")
def test_create_with_port(mock_create: MagicMock) -> None:
    container = MagicMock()
    container.name = "test"
    container.container_id = "abc123def456"
    mock_create.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "-p", "8080:80"])
    assert result.exit_code == 0
    call_kwargs = mock_create.call_args[1]
    assert call_kwargs["ports"] == {8080: 80}


@patch("pocketdock.create_new_container")
def test_create_with_multiple_ports(mock_create: MagicMock) -> None:
    container = MagicMock()
    container.name = "test"
    container.container_id = "abc123def456"
    mock_create.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "-p", "8080:80", "-p", "3000:3000"])
    assert result.exit_code == 0
    call_kwargs = mock_create.call_args[1]
    assert call_kwargs["ports"] == {8080: 80, 3000: 3000}


@patch("pocketdock.create_new_container")
def test_create_port_invalid_format(mock_create: MagicMock) -> None:
    container = MagicMock()
    container.name = "test"
    container.container_id = "abc123"
    mock_create.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "-p", "not-a-port"])
    assert result.exit_code == 0
    call_kwargs = mock_create.call_args[1]
    assert "ports" not in call_kwargs


@patch("pocketdock.create_new_container")
def test_create_port_non_numeric(mock_create: MagicMock) -> None:
    container = MagicMock()
    container.name = "test"
    container.container_id = "abc123"
    mock_create.return_value = container
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "-p", "abc:def"])
    assert result.exit_code == 0
    call_kwargs = mock_create.call_args[1]
    assert "ports" not in call_kwargs


# --- build command ---


@patch("pocketdock._socket_client.build_image", new_callable=AsyncMock)
@patch("pocketdock._socket_client.detect_socket")
def test_build_single_profile(mock_detect: MagicMock, mock_build: AsyncMock) -> None:
    mock_detect.return_value = "/tmp/s.sock"
    mock_build.return_value = '{"stream":"ok"}'
    runner = CliRunner()
    result = runner.invoke(cli, ["build", "minimal"])
    assert result.exit_code == 0
    assert "Built" in result.output


@patch("pocketdock._socket_client.build_image", new_callable=AsyncMock)
@patch("pocketdock._socket_client.detect_socket")
def test_build_all_profiles(mock_detect: MagicMock, mock_build: AsyncMock) -> None:
    mock_detect.return_value = "/tmp/s.sock"
    mock_build.return_value = '{"stream":"ok"}'
    runner = CliRunner()
    result = runner.invoke(cli, ["build", "--all"])
    assert result.exit_code == 0
    assert result.output.count("Built") == 4


@patch("pocketdock._socket_client.build_image", new_callable=AsyncMock)
@patch("pocketdock._socket_client.detect_socket")
def test_build_default_builds_all(mock_detect: MagicMock, mock_build: AsyncMock) -> None:
    mock_detect.return_value = "/tmp/s.sock"
    mock_build.return_value = '{"stream":"ok"}'
    runner = CliRunner()
    result = runner.invoke(cli, ["build"])
    assert result.exit_code == 0
    assert result.output.count("Built") == 4


@patch("pocketdock._socket_client.detect_socket")
def test_build_no_engine(mock_detect: MagicMock) -> None:
    mock_detect.return_value = None
    runner = CliRunner()
    result = runner.invoke(cli, ["build", "minimal"])
    assert result.exit_code == 1


def test_build_unknown_profile() -> None:
    runner = CliRunner()
    with patch("pocketdock._socket_client.detect_socket", return_value="/tmp/s.sock"):
        result = runner.invoke(cli, ["build", "nonexistent"])
    assert result.exit_code == 1


@patch("pocketdock._socket_client.build_image")
@patch("pocketdock._socket_client.detect_socket")
def test_build_error(mock_detect: MagicMock, mock_build: MagicMock) -> None:
    mock_detect.return_value = "/tmp/s.sock"
    mock_build.side_effect = RuntimeError("build boom")
    runner = CliRunner()
    result = runner.invoke(cli, ["build", "minimal"])
    assert result.exit_code == 1


@patch("pocketdock._socket_client.build_image")
@patch("pocketdock._socket_client.detect_socket")
def test_build_pocketdock_error(mock_detect: MagicMock, mock_build: MagicMock) -> None:
    mock_detect.return_value = "/tmp/s.sock"
    mock_build.side_effect = PodmanNotRunning()
    runner = CliRunner()
    result = runner.invoke(cli, ["build", "minimal"])
    assert result.exit_code == 1


# --- export command ---


@patch("pocketdock._socket_client.save_image", new_callable=AsyncMock)
@patch("pocketdock._socket_client.detect_socket")
def test_export_with_image(mock_detect: MagicMock, mock_save: AsyncMock, tmp_path: Path) -> None:
    mock_detect.return_value = "/tmp/s.sock"
    mock_save.return_value = b"tar-data"
    out = str(tmp_path / "out.tar")
    runner = CliRunner()
    result = runner.invoke(cli, ["export", "--image", "pocketdock/minimal", "-o", out])
    assert result.exit_code == 0
    assert Path(out).read_bytes() == b"tar-data"


@patch("pocketdock._socket_client.save_image", new_callable=AsyncMock)
@patch("pocketdock._socket_client.detect_socket")
def test_export_with_profile(mock_detect: MagicMock, mock_save: AsyncMock, tmp_path: Path) -> None:
    mock_detect.return_value = "/tmp/s.sock"
    mock_save.return_value = b"tar-data"
    out = str(tmp_path / "out.tar")
    runner = CliRunner()
    result = runner.invoke(cli, ["export", "--profile", "dev", "-o", out])
    assert result.exit_code == 0


@patch("pocketdock._socket_client.save_image", new_callable=AsyncMock)
@patch("pocketdock._socket_client.detect_socket")
def test_export_all(mock_detect: MagicMock, mock_save: AsyncMock, tmp_path: Path) -> None:
    mock_detect.return_value = "/tmp/s.sock"
    mock_save.return_value = b"tar-data"
    out = str(tmp_path / "out.tar")
    runner = CliRunner()
    result = runner.invoke(cli, ["export", "--all", "-o", out])
    assert result.exit_code == 0


@patch("pocketdock._socket_client.save_image", new_callable=AsyncMock)
@patch("pocketdock._socket_client.detect_socket")
def test_export_gzip(mock_detect: MagicMock, mock_save: AsyncMock, tmp_path: Path) -> None:
    import gzip

    mock_detect.return_value = "/tmp/s.sock"
    mock_save.return_value = b"tar-data"
    out = str(tmp_path / "out.tar.gz")
    runner = CliRunner()
    result = runner.invoke(cli, ["export", "--image", "test", "-o", out])
    assert result.exit_code == 0
    # Verify it's gzip-compressed
    decompressed = gzip.decompress(Path(out).read_bytes())
    assert decompressed == b"tar-data"


@patch("pocketdock._socket_client.detect_socket")
def test_export_no_engine(mock_detect: MagicMock, tmp_path: Path) -> None:
    mock_detect.return_value = None
    out = str(tmp_path / "out.tar")
    runner = CliRunner()
    result = runner.invoke(cli, ["export", "--image", "test", "-o", out])
    assert result.exit_code == 1


def test_export_no_image_or_profile(tmp_path: Path) -> None:
    out = str(tmp_path / "out.tar")
    runner = CliRunner()
    with patch("pocketdock._socket_client.detect_socket", return_value="/tmp/s.sock"):
        result = runner.invoke(cli, ["export", "-o", out])
    assert result.exit_code != 0


@patch("pocketdock._socket_client.save_image")
@patch("pocketdock._socket_client.detect_socket")
def test_export_error(mock_detect: MagicMock, mock_save: MagicMock, tmp_path: Path) -> None:
    mock_detect.return_value = "/tmp/s.sock"
    mock_save.side_effect = RuntimeError("save boom")
    out = str(tmp_path / "out.tar")
    runner = CliRunner()
    result = runner.invoke(cli, ["export", "--image", "test", "-o", out])
    assert result.exit_code == 1


@patch("pocketdock._socket_client.save_image")
@patch("pocketdock._socket_client.detect_socket")
def test_export_pocketdock_error(
    mock_detect: MagicMock, mock_save: MagicMock, tmp_path: Path
) -> None:
    from pocketdock.errors import ImageNotFound

    mock_detect.return_value = "/tmp/s.sock"
    mock_save.side_effect = ImageNotFound("nope")
    out = str(tmp_path / "out.tar")
    runner = CliRunner()
    result = runner.invoke(cli, ["export", "--image", "nope", "-o", out])
    assert result.exit_code == 1


# --- import command ---


@patch("pocketdock._socket_client.load_image", new_callable=AsyncMock)
@patch("pocketdock._socket_client.detect_socket")
def test_import_success(mock_detect: MagicMock, mock_load: AsyncMock, tmp_path: Path) -> None:
    mock_detect.return_value = "/tmp/s.sock"
    mock_load.return_value = "ok"
    tar_file = tmp_path / "images.tar"
    tar_file.write_bytes(b"tar-data")
    runner = CliRunner()
    result = runner.invoke(cli, ["import", str(tar_file)])
    assert result.exit_code == 0
    assert "Imported" in result.output


@patch("pocketdock._socket_client.load_image", new_callable=AsyncMock)
@patch("pocketdock._socket_client.detect_socket")
def test_import_gzip(mock_detect: MagicMock, mock_load: AsyncMock, tmp_path: Path) -> None:
    import gzip

    mock_detect.return_value = "/tmp/s.sock"
    mock_load.return_value = "ok"
    gz_file = tmp_path / "images.tar.gz"
    gz_file.write_bytes(gzip.compress(b"tar-data"))
    runner = CliRunner()
    result = runner.invoke(cli, ["import", str(gz_file)])
    assert result.exit_code == 0
    # Verify the decompressed data was passed
    call_args = mock_load.call_args[0]
    assert call_args[1] == b"tar-data"


@patch("pocketdock._socket_client.detect_socket")
def test_import_no_engine(mock_detect: MagicMock, tmp_path: Path) -> None:
    mock_detect.return_value = None
    tar_file = tmp_path / "images.tar"
    tar_file.write_bytes(b"data")
    runner = CliRunner()
    result = runner.invoke(cli, ["import", str(tar_file)])
    assert result.exit_code == 1


@patch("pocketdock._socket_client.load_image")
@patch("pocketdock._socket_client.detect_socket")
def test_import_error(mock_detect: MagicMock, mock_load: MagicMock, tmp_path: Path) -> None:
    mock_detect.return_value = "/tmp/s.sock"
    mock_load.side_effect = RuntimeError("load boom")
    tar_file = tmp_path / "images.tar"
    tar_file.write_bytes(b"data")
    runner = CliRunner()
    result = runner.invoke(cli, ["import", str(tar_file)])
    assert result.exit_code == 1


@patch("pocketdock._socket_client.load_image")
@patch("pocketdock._socket_client.detect_socket")
def test_import_pocketdock_error(
    mock_detect: MagicMock, mock_load: MagicMock, tmp_path: Path
) -> None:
    mock_detect.return_value = "/tmp/s.sock"
    mock_load.side_effect = PodmanNotRunning()
    tar_file = tmp_path / "images.tar"
    tar_file.write_bytes(b"data")
    runner = CliRunner()
    result = runner.invoke(cli, ["import", str(tar_file)])
    assert result.exit_code == 1


def test_import_nonexistent_file() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["import", "/nonexistent/file.tar"])
    assert result.exit_code != 0


# --- profiles command ---


def test_profiles_list() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["profiles"])
    assert result.exit_code == 0
    assert "minimal" in result.output
    assert "dev" in result.output
    assert "agent" in result.output
    assert "embedded" in result.output


def test_profiles_json() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["profiles", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 4
    names = {p["name"] for p in data}
    assert names == {"minimal", "dev", "agent", "embedded"}


def test_profiles_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["profiles", "--help"])
    assert result.exit_code == 0


# --- build help ---


def test_build_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["build", "--help"])
    assert result.exit_code == 0


# --- export help ---


def test_export_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["export", "--help"])
    assert result.exit_code == 0


# --- import help ---


def test_import_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["import", "--help"])
    assert result.exit_code == 0
