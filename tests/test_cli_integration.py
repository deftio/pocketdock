"""Integration tests for CLI commands that require a real container engine."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from click.testing import CliRunner
from pocketdock import _socket_client as sc
from pocketdock.cli.main import cli

from .conftest import requires_engine

if TYPE_CHECKING:
    import pytest


# --- Helper ---


async def _force_cleanup(name: str) -> None:
    """Best-effort cleanup of a container by name."""
    socket_path = sc.detect_socket()
    if socket_path is None:
        return
    with contextlib.suppress(Exception):
        containers = await sc.list_containers(
            socket_path, label_filter=f"pocketdock.instance={name}"
        )
        for ct in containers:
            with contextlib.suppress(Exception):
                await sc.remove_container(socket_path, ct["Id"], force=True)


# --- profiles command ---


@requires_engine
def test_cli_profiles_lists_all() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["profiles"])
    assert result.exit_code == 0
    assert "minimal" in result.output
    assert "dev" in result.output
    assert "agent" in result.output
    assert "embedded" in result.output


@requires_engine
def test_cli_profiles_json() -> None:
    import json

    runner = CliRunner()
    result = runner.invoke(cli, ["profiles", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 4


# --- create with profile ---


@requires_engine
async def test_cli_create_with_profile() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["create", "--profile", "minimal", "--name", "pd-cli-int-profile"])
    try:
        assert result.exit_code == 0
        assert "pd-cli-int-profile" in result.output
    finally:
        await _force_cleanup("pd-cli-int-profile")


# --- build (minimal only — fast) ---


@requires_engine
def test_cli_build_minimal() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["build", "minimal"])
    assert result.exit_code == 0
    assert "Built" in result.output


# --- export/import round trip ---


@requires_engine
def test_cli_export_import_roundtrip(tmp_path: pytest.TempPathFactory) -> None:
    out = str(tmp_path / "minimal.tar")  # type: ignore[operator]
    runner = CliRunner()
    # Export
    result = runner.invoke(cli, ["export", "--image", "pocketdock/minimal", "-o", out])
    assert result.exit_code == 0
    assert "Exported" in result.output
    # Import
    result = runner.invoke(cli, ["import", out])
    assert result.exit_code == 0
    assert "Imported" in result.output
