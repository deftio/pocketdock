# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""CLI entry point for pocketdock."""

from __future__ import annotations

import dataclasses

import click

from pocketdock import __version__


@dataclasses.dataclass
class CliContext:
    """Shared state passed through Click's context object."""

    socket: str | None = None
    verbose: bool = False
    json_output: bool = False


@click.group()
@click.option(
    "--socket",
    envvar="POCKETDOCK_SOCKET",
    default=None,
    help="Path to container engine socket.",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output.")
@click.version_option(version=__version__, prog_name="pocketdock")
@click.pass_context
def cli(ctx: click.Context, socket: str | None, *, verbose: bool) -> None:
    """Portable container sandboxes for LLM agents and dev workflows."""
    ctx.ensure_object(dict)
    ctx.obj = CliContext(socket=socket, verbose=verbose)


# --- Register commands ---

from pocketdock.cli._commands import (  # noqa: E402
    build_cmd,
    create_cmd,
    doctor_cmd,
    export_cmd,
    import_cmd,
    info_cmd,
    init_cmd,
    list_cmd,
    logs_cmd,
    profiles_cmd,
    prune_cmd,
    pull_cmd,
    push_cmd,
    quickstart_cmd,
    reboot_cmd,
    resume_cmd,
    run_cmd,
    shell_cmd,
    shutdown_cmd,
    snapshot_cmd,
    status_cmd,
    stop_cmd,
)

cli.add_command(quickstart_cmd)
cli.add_command(init_cmd)
cli.add_command(list_cmd)
cli.add_command(info_cmd)
cli.add_command(doctor_cmd)
cli.add_command(status_cmd)
cli.add_command(logs_cmd)
cli.add_command(create_cmd)
cli.add_command(run_cmd)
cli.add_command(push_cmd)
cli.add_command(pull_cmd)
cli.add_command(reboot_cmd)
cli.add_command(stop_cmd)
cli.add_command(resume_cmd)
cli.add_command(shutdown_cmd)
cli.add_command(snapshot_cmd)
cli.add_command(prune_cmd)
cli.add_command(shell_cmd)
cli.add_command(build_cmd)
cli.add_command(export_cmd)
cli.add_command(import_cmd, name="import")
cli.add_command(profiles_cmd)
