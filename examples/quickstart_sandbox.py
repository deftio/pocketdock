# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Quickstart: Run a program in a sandbox.

Creates a container, writes a Python script into it, executes it,
and prints the results. Shows the core create -> write -> run -> read loop.

Usage:
    python examples/quickstart_sandbox.py
"""

import pocketdock

SCRIPT = """\
import math
import platform

print(f"Hello from {platform.system()} {platform.machine()}!")
print(f"Python {platform.python_version()}")
print(f"pi = {math.pi:.10f}")
print(f"e  = {math.e:.10f}")
print(f"sqrt(2) = {math.sqrt(2):.10f}")
"""


def main() -> None:
    print("Creating sandbox container ...")
    c = pocketdock.create_new_container()

    try:
        c.write_file("/home/sandbox/demo.py", SCRIPT)
        result = c.run("python3 /home/sandbox/demo.py")

        print()
        if result.ok:
            print(result.stdout)
        else:
            print(f"Script failed (exit code {result.exit_code})")
            if result.stderr:
                print(result.stderr)
        print(f"Completed in {result.duration_ms:.0f}ms")
    finally:
        c.shutdown()
        print("Container stopped.")


if __name__ == "__main__":
    main()
