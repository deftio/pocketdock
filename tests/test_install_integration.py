# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Integration test: install pocketdock inside a pocketdock container.

Verifies that ``pip install pocketdock`` (bare, no extras) produces a working
CLI.  This catches dependency issues that unit tests cannot: the container has
a clean Python with no pre-installed packages.

The test builds a wheel from the local source tree, pushes it into the
container, and installs it — so it always tests the current code, not
whatever is on PyPI.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from pocketdock import create_new_container

from .conftest import requires_engine

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@requires_engine
def test_pip_install_bare_cli_works(tmp_path: Path) -> None:
    """Bare ``pip install pocketdock`` (no extras) should give a working CLI."""
    # Build a wheel from the local source tree.
    subprocess.run(  # noqa: S603
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path)],
        cwd=str(_PROJECT_ROOT),
        check=True,
        capture_output=True,
    )
    wheels = list(tmp_path.glob("pocketdock-*.whl"))
    assert wheels, "wheel build produced no output"
    whl = wheels[0]

    with create_new_container() as c:
        # Push the wheel into the container.
        c.push(str(whl), f"/tmp/{whl.name}")

        # Install from the local wheel (not PyPI).
        # --break-system-packages is needed on Alpine (PEP 668).
        r = c.run(
            f"pip install --break-system-packages /tmp/{whl.name}",
            timeout=120,
        )
        assert r.ok, f"pip install failed: {r.stderr}"

        # pip installs console scripts to ~/.local/bin which may not be on PATH.
        pd = "/home/sandbox/.local/bin/pocketdock"

        # The console script must exist and respond to --version.
        r = c.run(f"{pd} --version")
        assert r.ok, f"pocketdock --version failed: {r.stderr}"
        assert "pocketdock" in r.stdout

        # The quickstart command must work (proves click + rich loaded).
        r = c.run(f"{pd} quickstart")
        assert r.ok, f"pocketdock quickstart failed: {r.stderr}"
        assert "build" in r.stdout.lower()

        # The profiles command must list all profiles.
        r = c.run(f"{pd} profiles")
        assert r.ok, f"pocketdock profiles failed: {r.stderr}"
        assert "minimal-python" in r.stdout
