# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""Quickstart: Hello World web server in a container.

Creates a container with port 8080 mapped, writes an HTML page,
starts a Python HTTP server, and waits for you to visit it in a browser.

Usage:
    python examples/quickstart_webserver.py

Then open http://localhost:8080 in your browser.
Press Enter to stop the container.
"""

import pocketdock

HTML = """\
<!DOCTYPE html>
<html>
<head>
  <title>pocketdock</title>
  <style>
    body { font-family: system-ui, sans-serif; display: flex;
           justify-content: center; align-items: center; height: 100vh;
           margin: 0; background: #1a1a2e; color: #eee; }
    .card { background: #16213e; padding: 2rem 3rem; border-radius: 12px;
            box-shadow: 0 4px 24px rgba(0,0,0,0.3); text-align: center; }
    h1 { margin: 0 0 0.5rem; }
    p  { color: #aaa; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Hello from pocketdock!</h1>
    <p>Served from inside a container on port 8080.</p>
  </div>
</body>
</html>
"""


def main() -> None:
    print("Creating container with port 8080 mapped ...")
    c = pocketdock.create_new_container(ports={8080: 8080})

    try:
        c.write_file("/srv/index.html", HTML)
        proc = c.run(
            "python3 -m http.server 8080 --directory /srv",
            detach=True,
        )
        print(f"Container {c.name} is running ({c.container_id[:12]})")
        print(f"Web server started (exec {proc.id[:12]})")
        print()
        print("  Open http://localhost:8080 in your browser")
        print()
        input("Press Enter to stop ...")
    finally:
        c.shutdown()
        print("Container stopped.")


if __name__ == "__main__":
    main()
