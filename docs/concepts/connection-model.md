# Connection Model

## Connection-per-Operation

Every SDK operation opens its own Unix socket connection, performs the HTTP request, and closes the connection. There is no connection pooling, no persistent connections, and no multiplexing.

```
c.run("echo hello")    → open socket → HTTP POST /exec → close socket
c.info()               → open socket → HTTP GET /inspect → close socket
c.write_file(...)      → open socket → HTTP PUT /archive → close socket
```

Each operation is fully independent.

### Why No Pooling?

Unix socket connections are essentially free:

- **No TCP handshake** — no SYN/SYN-ACK/ACK round trip
- **No TLS negotiation** — communication is local, within the same machine
- **No DNS resolution** — the socket is a filesystem path
- **Kernel-level routing** — data moves through kernel buffers, not the network stack

The cost of opening a Unix socket connection is on the order of microseconds. Connection pooling would add complexity (lifecycle management, health checks, thread safety) without meaningful performance benefit.

### Isolation Benefits

Connection-per-operation means:

- **Streaming doesn't block other operations** — a long-running `run(stream=True)` holds its own connection while `info()`, `write_file()`, or another `run()` can proceed on separate connections
- **No head-of-line blocking** — each operation's I/O is independent
- **Clean error handling** — if a connection fails, only that operation is affected
- **No stale connections** — no risk of using a connection that the engine has closed

## Socket Auto-Detection

If no socket path is specified, pocketdock searches in this order:

| Priority | Path | Engine | Platform |
|----------|------|--------|----------|
| 1 | `$POCKETDOCK_SOCKET` env var | Any | All |
| 2 | `$XDG_RUNTIME_DIR/podman/podman.sock` | Podman (rootless) | Linux |
| 3 | `/run/podman/podman.sock` | Podman (system) | Linux |
| 4 | `/var/run/docker.sock` | Docker | All |
| 5 | `~/.local/share/containers/podman/machine/.../podman.sock` | Podman Machine | macOS |
| 6 | `~/.docker/run/docker.sock` | Docker Desktop | macOS |

Detection checks that the socket file exists and is connectable. The first working socket wins.

### Override

Specify a socket explicitly:

```python
c = create_new_container(socket_path="/path/to/engine.sock")
```

Or via environment variable:

```bash
export POCKETDOCK_SOCKET=/path/to/engine.sock
```

Or via project config (`pocketdock.yaml`):

```yaml
socket: /path/to/engine.sock
```

## Concurrency Model

### Async Operations

Multiple async operations can run concurrently on the same container:

```python
import asyncio
from pocketdock.async_ import create_new_container

async def main():
    async with await create_new_container() as c:
        # These run concurrently, each on its own socket connection
        r1, r2 = await asyncio.gather(
            c.run("echo one"),
            c.run("echo two"),
        )
```

### Sync Operations

Sync operations are serialized per call (each blocks until complete), but multiple threads can operate on different containers simultaneously. The sync facade uses a shared background event loop thread.

### Streaming and Detached

A streaming or detached process holds its socket connection open for the duration of the stream/process. Other operations on the same container are unaffected because they open their own connections.

```python
# This works fine — the stream and run() use separate connections
stream = c.run("make all", stream=True)
for chunk in stream:
    if "error" in chunk.data:
        # Run a diagnostic command while streaming
        info = c.info()
        print(f"Memory: {info.memory_usage}")
```

## Engine Compatibility

pocketdock supports both Podman and Docker. The socket client handles differences transparently:

| Feature | Docker | Podman |
|---------|--------|--------|
| Stream framing | 8-byte demux headers | Raw stream (no framing) |
| Chunked encoding | Always | Sometimes |
| Container name prefix | `/name` | `name` |
| Default socket | `/var/run/docker.sock` | `$XDG_RUNTIME_DIR/podman/podman.sock` |
| Rootless | No | Yes (default) |

The API endpoints are compatible — both engines implement the same REST API for container operations.
