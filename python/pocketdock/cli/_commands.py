# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""CLI command implementations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from pocketdock import Container
    from pocketdock.cli.main import CliContext

from pocketdock.cli._output import (
    format_container_info,
    format_container_list,
    format_doctor_report,
    format_error,
    print_success,
)


def _get_ctx(ctx: click.Context) -> CliContext:
    """Extract the CliContext from Click's context object."""
    return ctx.obj  # type: ignore[no-any-return]


def _resolve_container(name: str, socket_path: str | None) -> Container:
    """Resolve a container by name. Returns a Container handle or raises SystemExit."""
    import pocketdock  # noqa: PLC0415

    try:
        return pocketdock.resume_container(name, socket_path=socket_path)
    except pocketdock.PocketDockError as exc:
        format_error(exc)
        raise SystemExit(1) from exc


# ---------------------------------------------------------------------------
# Read-only commands
# ---------------------------------------------------------------------------


@click.command("init")
@click.option("--name", default=None, help="Project name (defaults to directory name).")
@click.argument("path", required=False, default=None)
def init_cmd(name: str | None, path: str | None) -> None:
    """Initialize a pocketdock project."""
    import pocketdock  # noqa: PLC0415

    resolved = Path(path) if path else None
    try:
        root = pocketdock.init_project(resolved, project_name=name)
    except pocketdock.PocketDockError as exc:
        format_error(exc)
        raise SystemExit(1) from exc
    print_success(f"Project initialized at {root}")


@click.command("list")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
@click.option("--project", default=None, help="Filter by project name.")
@click.pass_context
def list_cmd(ctx: click.Context, *, json_output: bool, project: str | None) -> None:
    """List pocketdock containers."""
    import pocketdock  # noqa: PLC0415

    cli_ctx = _get_ctx(ctx)
    try:
        items = pocketdock.list_containers(socket_path=cli_ctx.socket, project=project)
    except pocketdock.PocketDockError as exc:
        format_error(exc)
        raise SystemExit(1) from exc
    format_container_list(items, json_output=json_output)


@click.command("info")
@click.argument("container")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
@click.pass_context
def info_cmd(ctx: click.Context, container: str, *, json_output: bool) -> None:
    """Show detailed container information."""
    cli_ctx = _get_ctx(ctx)
    c = _resolve_container(container, cli_ctx.socket)
    try:
        info = c.info()
    except Exception as exc:
        from pocketdock.errors import PocketDockError  # noqa: PLC0415

        if isinstance(exc, PocketDockError):
            format_error(exc)
        raise SystemExit(1) from exc
    format_container_info(info, json_output=json_output)


@click.command("doctor")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
@click.pass_context
def doctor_cmd(ctx: click.Context, *, json_output: bool) -> None:
    """Diagnose project health."""
    import pocketdock  # noqa: PLC0415

    cli_ctx = _get_ctx(ctx)
    try:
        report = pocketdock.doctor(socket_path=cli_ctx.socket)
    except pocketdock.PocketDockError as exc:
        format_error(exc)
        raise SystemExit(1) from exc
    format_doctor_report(report, json_output=json_output)


@click.command("status")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
@click.pass_context
def status_cmd(ctx: click.Context, *, json_output: bool) -> None:
    """Show project status summary."""
    import pocketdock  # noqa: PLC0415
    from pocketdock.projects import get_project_name, list_instance_dirs  # noqa: PLC0415

    cli_ctx = _get_ctx(ctx)
    try:
        root = pocketdock.find_project_root()
        if root is None:
            from pocketdock.errors import ProjectNotInitialized  # noqa: PLC0415

            raise ProjectNotInitialized
        project_name = get_project_name(root)
        instances = list_instance_dirs(root)
        containers = pocketdock.list_containers(socket_path=cli_ctx.socket, project=project_name)
    except pocketdock.PocketDockError as exc:
        format_error(exc)
        raise SystemExit(1) from exc

    running = sum(1 for c in containers if c.status == "running")
    stopped = len(containers) - running

    if json_output:
        import sys  # noqa: PLC0415

        data = {
            "project": project_name,
            "root": str(root),
            "instances": len(instances),
            "containers": len(containers),
            "running": running,
            "stopped": stopped,
        }
        sys.stdout.write(json.dumps(data, indent=2, default=str) + "\n")
        return

    from rich.console import Console  # noqa: PLC0415
    from rich.panel import Panel  # noqa: PLC0415

    lines = [
        f"[bold]Project:[/bold]    {project_name}",
        f"[bold]Root:[/bold]       {root}",
        f"[bold]Instances:[/bold]  {len(instances)}",
        f"[bold]Containers:[/bold] {len(containers)}"
        f" ([green]{running} running[/green], [yellow]{stopped} stopped[/yellow])",
    ]
    Console().print(Panel("\n".join(lines), title="Project Status", expand=False))


# ---------------------------------------------------------------------------
# Logs helpers
# ---------------------------------------------------------------------------


def _read_history_entries(instance_dirs: list[Path]) -> list[dict[str, object]]:
    """Read JSONL history entries from instance directories."""
    entries: list[dict[str, object]] = []
    for inst_dir in instance_dirs:
        history = inst_dir / "logs" / "history.jsonl"
        if history.is_file():
            for raw in history.read_text().splitlines():
                stripped = raw.strip()
                if not stripped:
                    continue
                try:
                    entry = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                entry["_instance"] = inst_dir.name
                entries.append(entry)
    return entries


def _print_log_table(entries: list[dict[str, object]]) -> None:
    """Print log entries as a Rich table."""
    from rich.console import Console  # noqa: PLC0415
    from rich.table import Table  # noqa: PLC0415

    table = Table(title="Log History")
    table.add_column("Instance", style="cyan")
    table.add_column("Type")
    table.add_column("Command")
    table.add_column("Exit")
    table.add_column("Duration")
    table.add_column("Timestamp", style="dim")

    for entry in entries:
        exit_code = str(entry.get("exit_code", ""))
        exit_style = "green" if exit_code == "0" else "red" if exit_code else ""
        dur = entry.get("duration_ms")
        dur_str = f"{dur:.0f}ms" if isinstance(dur, (int, float)) else ""
        table.add_row(
            str(entry.get("_instance", "")),
            str(entry.get("type", "")),
            str(entry.get("command", ""))[:60],
            f"[{exit_style}]{exit_code}[/{exit_style}]" if exit_style else exit_code,
            dur_str,
            str(entry.get("timestamp", "")),
        )

    Console().print(table)


@click.command("logs")
@click.argument("container", required=False, default=None)
@click.option("--last", "last_n", type=int, default=10, help="Number of entries to show.")
@click.option(
    "--type",
    "entry_type",
    default=None,
    help="Filter by entry type (e.g. 'run', 'session').",
)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
def logs_cmd(
    container: str | None,
    *,
    last_n: int,
    entry_type: str | None,
    json_output: bool,
) -> None:
    """View container logs from history.jsonl."""
    import pocketdock  # noqa: PLC0415
    from pocketdock.projects import list_instance_dirs  # noqa: PLC0415

    root = pocketdock.find_project_root()
    if root is None:
        from pocketdock.errors import ProjectNotInitialized  # noqa: PLC0415

        err = ProjectNotInitialized()
        format_error(err)
        raise SystemExit(1) from err

    instance_dirs = list_instance_dirs(root)
    if container:
        instance_dirs = [d for d in instance_dirs if d.name == container]
        if not instance_dirs:
            click.echo(f"No instance directory found for '{container}'.", err=True)
            raise SystemExit(1)

    entries = _read_history_entries(instance_dirs)

    if entry_type:
        entries = [e for e in entries if e.get("type") == entry_type]

    entries = entries[-last_n:]

    if json_output:
        import sys  # noqa: PLC0415

        sys.stdout.write(json.dumps(entries, indent=2, default=str) + "\n")
        return

    if not entries:
        click.echo("No log entries found.")
        return

    _print_log_table(entries)


# ---------------------------------------------------------------------------
# Mutating commands
# ---------------------------------------------------------------------------


def _build_create_kwargs(  # noqa: PLR0913
    *,
    image: str | None,
    name: str | None,
    timeout: int,
    mem_limit: str | None,
    cpu_percent: int | None,
    persist: bool,
    volume: tuple[str, ...],
    project: str | None,
    profile: str | None = None,
    device: tuple[str, ...] = (),
) -> dict[str, object]:
    """Build kwargs dict for create_new_container from CLI options."""
    kwargs: dict[str, object] = {"timeout": timeout, "persist": persist}
    if image:
        kwargs["image"] = image
    if name:
        kwargs["name"] = name
    if mem_limit:
        kwargs["mem_limit"] = mem_limit
    if cpu_percent is not None:
        kwargs["cpu_percent"] = cpu_percent
    if project:
        kwargs["project"] = project
    if profile:
        kwargs["profile"] = profile
    if device:
        kwargs["devices"] = list(device)
    if volume:
        volumes = dict(
            pair
            for v in volume
            if len(pair := v.split(":", 1)) == 2  # noqa: PLR2004
        )
        if volumes:
            kwargs["volumes"] = volumes
    return kwargs


@click.command("create")
@click.option("--image", default=None, help="Container image (default: pocketdock/minimal).")
@click.option("--name", default=None, help="Container name.")
@click.option("--timeout", type=int, default=30, help="Default exec timeout in seconds.")
@click.option("--mem-limit", default=None, help="Memory limit (e.g. '256m', '1g').")
@click.option("--cpu-percent", type=int, default=None, help="CPU usage cap as percentage.")
@click.option("--persist", is_flag=True, help="Keep container on shutdown (stop, don't remove).")
@click.option("--volume", "-v", multiple=True, help="Volume mount HOST:CONTAINER.")
@click.option("--project", default=None, help="Project name.")
@click.option(
    "--profile",
    default=None,
    help="Image profile (minimal, dev, agent, embedded).",
)
@click.option(
    "--device", "-d", multiple=True, help="Host device to passthrough (e.g. /dev/ttyUSB0)."
)
@click.pass_context
def create_cmd(  # noqa: PLR0913
    ctx: click.Context,
    *,
    image: str | None,
    name: str | None,
    timeout: int,
    mem_limit: str | None,
    cpu_percent: int | None,
    persist: bool,
    volume: tuple[str, ...],
    project: str | None,
    profile: str | None,
    device: tuple[str, ...],
) -> None:
    """Create and start a new container."""
    import os  # noqa: PLC0415

    import pocketdock  # noqa: PLC0415

    cli_ctx = _get_ctx(ctx)
    kwargs = _build_create_kwargs(
        image=image,
        name=name,
        timeout=timeout,
        mem_limit=mem_limit,
        cpu_percent=cpu_percent,
        persist=persist,
        volume=volume,
        project=project,
        profile=profile,
        device=device,
    )

    old_env = os.environ.get("POCKETDOCK_SOCKET")
    if cli_ctx.socket:
        os.environ["POCKETDOCK_SOCKET"] = cli_ctx.socket
    try:
        c = pocketdock.create_new_container(**kwargs)  # type: ignore[arg-type]
    except pocketdock.PocketDockError as exc:
        format_error(exc)
        raise SystemExit(1) from exc
    finally:
        if cli_ctx.socket:
            if old_env is None:
                os.environ.pop("POCKETDOCK_SOCKET", None)
            else:
                os.environ["POCKETDOCK_SOCKET"] = old_env

    print_success(f"Container {c.name} created ({c.container_id[:12]})")


@click.command("run")
@click.argument("container")
@click.argument("command", nargs=-1, required=True)
@click.option("--timeout", type=int, default=None, help="Exec timeout in seconds.")
@click.option("--max-output", type=int, default=None, help="Max output bytes.")
@click.option("--lang", default=None, help="Language hint (e.g. 'python', 'bash').")
@click.option("--stream", "stream_mode", is_flag=True, help="Stream output in real-time.")
@click.option("--detach", is_flag=True, help="Run in background.")
@click.pass_context
def run_cmd(  # noqa: PLR0913
    ctx: click.Context,
    container: str,
    command: tuple[str, ...],
    *,
    timeout: int | None,
    max_output: int | None,
    lang: str | None,
    stream_mode: bool,
    detach: bool,
) -> None:
    """Execute a command inside a container."""
    cli_ctx = _get_ctx(ctx)
    c = _resolve_container(container, cli_ctx.socket)
    cmd_str = " ".join(command)

    try:
        if stream_mode:
            _run_stream(c, cmd_str, timeout, max_output, lang)
            return

        if detach:
            _run_detach(c, cmd_str, timeout, max_output, lang)
            return

        kw: dict[str, object] = {}
        if timeout is not None:
            kw["timeout"] = timeout
        if max_output is not None:
            kw["max_output"] = max_output
        if lang:
            kw["lang"] = lang
        result = c.run(cmd_str, **kw)  # type: ignore[call-overload]
    except Exception as exc:
        from pocketdock.errors import PocketDockError  # noqa: PLC0415

        if isinstance(exc, PocketDockError):
            format_error(exc)
        raise SystemExit(1) from exc

    from pocketdock.cli._output import format_exec_result  # noqa: PLC0415

    format_exec_result(result)
    raise SystemExit(result.exit_code)


def _run_stream(
    c: Container,
    cmd_str: str,
    timeout: float | None,
    max_output: int | None,
    lang: str | None,
) -> None:
    """Handle streaming mode for run command."""
    import sys  # noqa: PLC0415

    kw: dict[str, float | int | str] = {}
    if timeout is not None:
        kw["timeout"] = timeout
    if max_output is not None:
        kw["max_output"] = max_output
    if lang:
        kw["lang"] = lang
    for chunk in c.run(cmd_str, stream=True, **kw):  # type: ignore[call-overload]
        target = sys.stdout if chunk.stream == "stdout" else sys.stderr
        target.write(chunk.data)


def _run_detach(
    c: Container,
    cmd_str: str,
    timeout: float | None,
    max_output: int | None,
    lang: str | None,
) -> None:
    """Handle detach mode for run command."""
    kw: dict[str, float | int | str] = {}
    if timeout is not None:
        kw["timeout"] = timeout
    if max_output is not None:
        kw["max_output"] = max_output
    if lang:
        kw["lang"] = lang
    proc = c.run(cmd_str, detach=True, **kw)  # type: ignore[call-overload]
    print_success(f"Process started (exec ID: {proc.id})")


@click.command("push")
@click.argument("container")
@click.argument("src")
@click.argument("dst")
@click.pass_context
def push_cmd(ctx: click.Context, container: str, src: str, dst: str) -> None:
    """Copy files from host to container."""
    cli_ctx = _get_ctx(ctx)
    c = _resolve_container(container, cli_ctx.socket)
    try:
        c.push(src, dst)
    except Exception as exc:
        from pocketdock.errors import PocketDockError  # noqa: PLC0415

        if isinstance(exc, PocketDockError):
            format_error(exc)
        raise SystemExit(1) from exc
    print_success(f"Copied {src} -> {container}:{dst}")


@click.command("pull")
@click.argument("container")
@click.argument("src")
@click.argument("dst")
@click.pass_context
def pull_cmd(ctx: click.Context, container: str, src: str, dst: str) -> None:
    """Copy files from container to host."""
    cli_ctx = _get_ctx(ctx)
    c = _resolve_container(container, cli_ctx.socket)
    try:
        c.pull(src, dst)
    except Exception as exc:
        from pocketdock.errors import PocketDockError  # noqa: PLC0415

        if isinstance(exc, PocketDockError):
            format_error(exc)
        raise SystemExit(1) from exc
    print_success(f"Copied {container}:{src} -> {dst}")


@click.command("reboot")
@click.argument("container")
@click.option("--fresh", is_flag=True, help="Recreate with same config (new container).")
@click.pass_context
def reboot_cmd(ctx: click.Context, container: str, *, fresh: bool) -> None:
    """Restart a container."""
    cli_ctx = _get_ctx(ctx)
    c = _resolve_container(container, cli_ctx.socket)
    try:
        c.reboot(fresh=fresh)
    except Exception as exc:
        from pocketdock.errors import PocketDockError  # noqa: PLC0415

        if isinstance(exc, PocketDockError):
            format_error(exc)
        raise SystemExit(1) from exc
    mode = "fresh" if fresh else "in-place"
    print_success(f"Container {container} rebooted ({mode})")


@click.command("stop")
@click.argument("container")
@click.pass_context
def stop_cmd(ctx: click.Context, container: str) -> None:
    """Stop a running container (without removing)."""
    import pocketdock  # noqa: PLC0415

    cli_ctx = _get_ctx(ctx)
    try:
        pocketdock.stop_container(container, socket_path=cli_ctx.socket)
    except pocketdock.PocketDockError as exc:
        format_error(exc)
        raise SystemExit(1) from exc
    print_success(f"Container {container} stopped")


@click.command("resume")
@click.argument("container")
@click.pass_context
def resume_cmd(ctx: click.Context, container: str) -> None:
    """Resume a stopped persistent container."""
    cli_ctx = _get_ctx(ctx)
    c = _resolve_container(container, cli_ctx.socket)
    print_success(f"Container {container} resumed ({c.container_id[:12]})")


@click.command("shutdown")
@click.argument("container")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def shutdown_cmd(ctx: click.Context, container: str, *, yes: bool) -> None:
    """Stop and remove a container."""
    import pocketdock  # noqa: PLC0415
    from pocketdock.cli._output import confirm_destructive  # noqa: PLC0415

    cli_ctx = _get_ctx(ctx)
    if not yes and not confirm_destructive(f"Shutdown and remove container '{container}'?"):
        click.echo("Aborted.")
        return

    try:
        pocketdock.destroy_container(container, socket_path=cli_ctx.socket)
    except pocketdock.PocketDockError as exc:
        format_error(exc)
        raise SystemExit(1) from exc
    print_success(f"Container {container} shut down and removed")


@click.command("snapshot")
@click.argument("container")
@click.argument("image_name")
@click.pass_context
def snapshot_cmd(ctx: click.Context, container: str, image_name: str) -> None:
    """Save a container's filesystem as a new image."""
    cli_ctx = _get_ctx(ctx)
    c = _resolve_container(container, cli_ctx.socket)
    try:
        image_id = c.snapshot(image_name)
    except Exception as exc:
        from pocketdock.errors import PocketDockError  # noqa: PLC0415

        if isinstance(exc, PocketDockError):
            format_error(exc)
        raise SystemExit(1) from exc
    print_success(f"Snapshot saved as {image_name} ({image_id[:12]})")


@click.command("prune")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.option("--project", default=None, help="Only prune containers in this project.")
@click.pass_context
def prune_cmd(ctx: click.Context, *, yes: bool, project: str | None) -> None:
    """Remove all stopped pocketdock containers."""
    import pocketdock  # noqa: PLC0415
    from pocketdock.cli._output import confirm_destructive  # noqa: PLC0415

    cli_ctx = _get_ctx(ctx)
    if not yes and not confirm_destructive("Remove all stopped pocketdock containers?"):
        click.echo("Aborted.")
        return

    try:
        count = pocketdock.prune(socket_path=cli_ctx.socket, project=project)
    except pocketdock.PocketDockError as exc:
        format_error(exc)
        raise SystemExit(1) from exc
    print_success(f"Removed {count} container(s)")


def _detect_engine_cli(socket_path: str | None) -> str:
    """Detect which container engine CLI to use (podman or docker)."""
    import shutil  # noqa: PLC0415

    if socket_path and "podman" in socket_path:
        return "podman"
    if socket_path and "docker" in socket_path:
        return "docker"
    if shutil.which("podman"):
        return "podman"
    return "docker"


@click.command("shell")
@click.argument("container")
@click.pass_context
def shell_cmd(ctx: click.Context, container: str) -> None:
    """Open an interactive shell inside a container."""
    import subprocess  # noqa: PLC0415  # nosec B404

    cli_ctx = _get_ctx(ctx)
    c = _resolve_container(container, cli_ctx.socket)
    engine = _detect_engine_cli(cli_ctx.socket)

    ret = subprocess.run(  # noqa: S603  # nosec B603
        [engine, "exec", "-it", c.container_id, "/bin/bash"],
        check=False,
    )
    if ret.returncode == 126:  # noqa: PLR2004
        ret = subprocess.run(  # noqa: S603  # nosec B603
            [engine, "exec", "-it", c.container_id, "/bin/sh"],
            check=False,
        )
    raise SystemExit(ret.returncode)


# ---------------------------------------------------------------------------
# Image management commands
# ---------------------------------------------------------------------------


def _build_tar_context(dockerfile_dir: Path) -> bytes:
    """Create a tar archive from a Dockerfile directory for the build API."""
    import io  # noqa: PLC0415
    import tarfile  # noqa: PLC0415

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for item in dockerfile_dir.iterdir():
            tar.add(str(item), arcname=item.name)
    return buf.getvalue()


@click.command("build")
@click.argument("profiles", nargs=-1)
@click.option("--all", "build_all", is_flag=True, help="Build all profiles.")
@click.pass_context
def build_cmd(ctx: click.Context, profiles: tuple[str, ...], *, build_all: bool) -> None:
    """Build image profiles from Dockerfiles."""
    import asyncio  # noqa: PLC0415

    from pocketdock import _socket_client as sc  # noqa: PLC0415
    from pocketdock.profiles import (  # noqa: PLC0415
        get_dockerfile_path,
        list_profiles,
        resolve_profile,
    )

    cli_ctx = _get_ctx(ctx)

    names = [p.name for p in list_profiles()] if build_all or not profiles else list(profiles)

    socket_path = cli_ctx.socket or sc.detect_socket()
    if socket_path is None:
        from pocketdock.errors import PodmanNotRunning  # noqa: PLC0415

        err = PodmanNotRunning()
        format_error(err)
        raise SystemExit(1) from err

    for name in names:
        try:
            info = resolve_profile(name)
        except ValueError as exc:
            click.echo(str(exc), err=True)
            raise SystemExit(1) from exc

        dockerfile_dir = get_dockerfile_path(name)
        context = _build_tar_context(dockerfile_dir)
        click.echo(f"Building {info.image_tag} ...")
        try:
            asyncio.run(sc.build_image(socket_path, context, info.image_tag))
        except Exception as exc:
            from pocketdock.errors import PocketDockError  # noqa: PLC0415

            if isinstance(exc, PocketDockError):
                format_error(exc)
            else:
                click.echo(f"Build failed: {exc}", err=True)
            raise SystemExit(1) from exc
        print_success(f"Built {info.image_tag}")


@click.command("export")
@click.option("--image", default=None, help="Image name to export.")
@click.option(
    "--profile",
    default=None,
    help="Profile name to export (resolves to image tag).",
)
@click.option("--all", "export_all", is_flag=True, help="Export all profile images.")
@click.option("-o", "--output", required=True, type=click.Path(), help="Output tar file path.")
@click.pass_context
def export_cmd(
    ctx: click.Context,
    *,
    image: str | None,
    profile: str | None,
    export_all: bool,
    output: str,
) -> None:
    """Export images to a tar file for air-gap transfer."""
    import asyncio  # noqa: PLC0415
    import gzip  # noqa: PLC0415

    from pocketdock import _socket_client as sc  # noqa: PLC0415

    cli_ctx = _get_ctx(ctx)
    socket_path = cli_ctx.socket or sc.detect_socket()
    if socket_path is None:
        from pocketdock.errors import PodmanNotRunning  # noqa: PLC0415

        err = PodmanNotRunning()
        format_error(err)
        raise SystemExit(1) from err

    image_names = _resolve_export_images(image=image, profile=profile, export_all=export_all)

    out_path = Path(output)
    for img_name in image_names:
        click.echo(f"Exporting {img_name} ...")
        try:
            tar_data = asyncio.run(sc.save_image(socket_path, img_name))
        except Exception as exc:
            from pocketdock.errors import PocketDockError  # noqa: PLC0415

            if isinstance(exc, PocketDockError):
                format_error(exc)
            else:
                click.echo(f"Export failed: {exc}", err=True)
            raise SystemExit(1) from exc

        if str(out_path).endswith(".gz"):
            out_path.write_bytes(gzip.compress(tar_data))
        else:
            out_path.write_bytes(tar_data)

    print_success(f"Exported to {output}")


def _resolve_export_images(
    *,
    image: str | None,
    profile: str | None,
    export_all: bool,
) -> list[str]:
    """Determine image names for export."""
    from pocketdock.profiles import list_profiles, resolve_profile  # noqa: PLC0415

    if export_all:
        return [p.image_tag for p in list_profiles()]
    if profile:
        return [resolve_profile(profile).image_tag]
    if image:
        return [image]
    msg = "Specify --image, --profile, or --all"
    raise click.UsageError(msg)


@click.command("import")
@click.argument("file", type=click.Path(exists=True))
@click.pass_context
def import_cmd(ctx: click.Context, file: str) -> None:
    """Import images from a tar file."""
    import asyncio  # noqa: PLC0415
    import gzip  # noqa: PLC0415

    from pocketdock import _socket_client as sc  # noqa: PLC0415

    cli_ctx = _get_ctx(ctx)
    socket_path = cli_ctx.socket or sc.detect_socket()
    if socket_path is None:
        from pocketdock.errors import PodmanNotRunning  # noqa: PLC0415

        err = PodmanNotRunning()
        format_error(err)
        raise SystemExit(1) from err

    file_path = Path(file)
    raw = file_path.read_bytes()
    if file.endswith(".gz"):
        raw = gzip.decompress(raw)

    click.echo(f"Importing from {file} ...")
    try:
        asyncio.run(sc.load_image(socket_path, raw))
    except Exception as exc:
        from pocketdock.errors import PocketDockError  # noqa: PLC0415

        if isinstance(exc, PocketDockError):
            format_error(exc)
        else:
            click.echo(f"Import failed: {exc}", err=True)
        raise SystemExit(1) from exc
    print_success(f"Imported from {file}")


@click.command("profiles")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
def profiles_cmd(*, json_output: bool) -> None:
    """List available image profiles."""
    from pocketdock.profiles import list_profiles  # noqa: PLC0415

    all_profiles = list_profiles()
    if json_output:
        import dataclasses  # noqa: PLC0415

        from pocketdock.cli._output import click_echo_json  # noqa: PLC0415

        click_echo_json([dataclasses.asdict(p) for p in all_profiles])
        return

    from rich.console import Console  # noqa: PLC0415
    from rich.table import Table  # noqa: PLC0415

    table = Table(title="Image Profiles")
    table.add_column("Name", style="cyan")
    table.add_column("Image Tag")
    table.add_column("Network")
    table.add_column("Size")
    table.add_column("Description")

    for p in all_profiles:
        net = "[green]enabled[/green]" if p.network_default else "[yellow]disabled[/yellow]"
        table.add_row(p.name, p.image_tag, net, p.size_estimate, p.description)

    Console().print(table)
