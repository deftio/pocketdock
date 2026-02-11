# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Rich output formatters for the CLI."""

from __future__ import annotations

import dataclasses
import json
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pocketdock.errors import PocketDockError
    from pocketdock.types import ContainerInfo, ContainerListItem, DoctorReport, ExecResult

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

_console = Console()
_err_console = Console(stderr=True)


def format_container_list(items: list[ContainerListItem], *, json_output: bool = False) -> None:
    """Print a list of containers as a rich table or JSON."""
    if json_output:
        rows = [dataclasses.asdict(item) for item in items]
        click_echo_json(rows)
        return

    if not items:
        _console.print("[dim]No containers found.[/dim]")
        return

    table = Table(title="Containers")
    table.add_column("Name", style="cyan")
    table.add_column("ID", style="dim")
    table.add_column("Status")
    table.add_column("Image")
    table.add_column("Persist")
    table.add_column("Project", style="dim")

    for item in items:
        status_style = "green" if item.status == "running" else "yellow"
        table.add_row(
            item.name,
            item.id,
            f"[{status_style}]{item.status}[/{status_style}]",
            item.image,
            "yes" if item.persist else "no",
            item.project,
        )

    _console.print(table)


def format_container_info(info: ContainerInfo, *, json_output: bool = False) -> None:
    """Print container info as a rich panel or JSON."""
    if json_output:
        d = dataclasses.asdict(info)
        click_echo_json(d)
        return

    status_style = "green" if info.status == "running" else "yellow"
    lines = [
        f"[bold]ID:[/bold]       {info.id[:12]}",
        f"[bold]Name:[/bold]     {info.name}",
        f"[bold]Status:[/bold]   [{status_style}]{info.status}[/{status_style}]",
        f"[bold]Image:[/bold]    {info.image}",
    ]
    if info.memory_usage:
        lines.append(f"[bold]Memory:[/bold]   {info.memory_usage} / {info.memory_limit}")
    if info.cpu_percent > 0:
        lines.append(f"[bold]CPU:[/bold]      {info.cpu_percent:.1f}%")
    if info.pids:
        lines.append(f"[bold]PIDs:[/bold]     {info.pids}")
    if info.ip_address:
        lines.append(f"[bold]IP:[/bold]       {info.ip_address}")

    panel = Panel("\n".join(lines), title=f"[cyan]{info.name}[/cyan]", expand=False)
    _console.print(panel)


def format_exec_result(result: ExecResult) -> None:
    """Print exec result stdout/stderr to their respective streams."""
    if result.stdout:
        sys.stdout.write(result.stdout)
        if not result.stdout.endswith("\n"):
            sys.stdout.write("\n")
    if result.stderr:
        sys.stderr.write(result.stderr)
        if not result.stderr.endswith("\n"):
            sys.stderr.write("\n")


def format_doctor_report(report: DoctorReport, *, json_output: bool = False) -> None:
    """Print doctor report as a rich panel or JSON."""
    if json_output:
        click_echo_json(dataclasses.asdict(report))
        return

    lines: list[str] = []
    if report.healthy:
        lines.append(f"[green]Healthy:[/green] {report.healthy} container(s)")
    if report.orphaned_containers:
        lines.append(
            f"[yellow]Orphaned containers:[/yellow] {', '.join(report.orphaned_containers)}"
        )
    if report.stale_instance_dirs:
        lines.append(
            f"[yellow]Stale instance dirs:[/yellow] {', '.join(report.stale_instance_dirs)}"
        )
    if not lines:
        lines.append("[dim]Nothing to report.[/dim]")

    panel = Panel("\n".join(lines), title="Doctor Report", expand=False)
    _console.print(panel)


def format_error(err: PocketDockError) -> None:
    """Print an SDK error as a rich panel with suggestions."""
    title, suggestion = _error_info(err)
    lines = [str(err)]
    if suggestion:
        lines.append(f"\n[dim]{suggestion}[/dim]")

    panel = Panel(
        "\n".join(lines),
        title=f"[red]{title}[/red]",
        expand=False,
    )
    _err_console.print(panel)


def _error_info(err: PocketDockError) -> tuple[str, str]:
    """Map an SDK error to a title and suggestion string."""
    from pocketdock.errors import (  # noqa: PLC0415
        ContainerNotFound,
        ImageNotFound,
        PodmanNotRunning,
        ProjectNotInitialized,
    )

    if isinstance(err, PodmanNotRunning):
        return "Engine Not Found", "Start Podman or Docker and try again."
    if isinstance(err, ContainerNotFound):
        return "Container Not Found", "Run 'pocketdock list' to see available containers."
    if isinstance(err, ImageNotFound):
        return "Image Not Found", "Pull the image first: docker pull <image>"
    if isinstance(err, ProjectNotInitialized):
        return "Project Not Initialized", "Run 'pocketdock init' to create a project."
    return "Error", ""


def print_success(msg: str) -> None:
    """Print a success message with a checkmark."""
    _console.print(f"[green]\u2713[/green] {msg}")


def confirm_destructive(msg: str) -> bool:
    """Prompt for confirmation. Returns True if confirmed."""
    return _console.input(f"[yellow]{msg} [y/N]:[/yellow] ").strip().lower() == "y"


def click_echo_json(data: object) -> None:
    """Serialize data to JSON and echo to stdout."""
    sys.stdout.write(json.dumps(data, indent=2, default=str) + "\n")
