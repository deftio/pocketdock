# pocketdock Examples

This directory contains examples demonstrating pocketdock's Python SDK.

## Quickstart

### Web Server (`quickstart_webserver.py`)

Spins up a container with port 8080 mapped to the host, writes an HTML page,
and starts a Python HTTP server. Open <http://localhost:8080> to see it live.

```bash
python examples/quickstart_webserver.py
```

### Sandbox (`quickstart_sandbox.py`)

Creates a container, writes a Python script into it, runs it, and prints the
output. Demonstrates the core create → write → run → read-results loop.

```bash
python examples/quickstart_sandbox.py
```

See the [documentation](https://deftio.github.io/pocketdock/) for the full guide.
