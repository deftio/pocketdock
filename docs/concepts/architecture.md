# Architecture

pocket-dock talks directly to Podman (or Docker) over its Unix socket using raw HTTP/1.1. The core SDK has zero external dependencies — it uses only Python stdlib modules.

## System Diagram

```
User Code / LLM Agent / CLI
        │
        ▼
  pocket-dock SDK
  ┌──────────────────────────────────────┐
  │ Container (sync) ──► AsyncContainer  │  facade pattern
  │   └─ _socket_client (raw HTTP/Unix) │
  ├─ ProjectManager (.pocket-dock/)      │
  ├─ Persistence (resume, snapshot)      │
  ├─ Sessions (persistent shells)        │
  ├─ Profiles (image registry)           │
  └──────────────────────────────────────┘
        │  raw HTTP over Unix socket
        │  (one connection per operation)
        ▼
  Podman (rootless) / Docker Engine
```

## Module Map

```
python/pocket_dock/
├── __init__.py              # Sync public exports
├── async_.py                # Async public exports
├── _async_container.py      # AsyncContainer (core implementation)
├── _sync_container.py       # Container (sync facade + _LoopThread)
├── _socket_client.py        # Async HTTP-over-Unix-socket client
├── _helpers.py              # Parsing utilities (bytes, timestamps, CPU)
├── _stream.py               # Stream demux, chunked encoding
├── _process.py              # Detached Process handle
├── _buffer.py               # Ring buffer (1MB default)
├── _session.py              # Persistent shell via long-lived exec
├── _callbacks.py            # Callback registry
├── _logger.py               # Auto stream-to-disk logging
├── _config.py               # Config loading (pocket-dock.yaml)
├── pool.py                  # ContainerPool (future)
├── persistence.py           # resume, snapshot, list, destroy, prune
├── projects.py              # .pocket-dock/ management
├── profiles.py              # Image profiles registry
├── errors.py                # Exception hierarchy
├── types.py                 # Data classes (ExecResult, ContainerInfo, etc.)
└── cli/                     # Click + Rich CLI
    ├── main.py              # Entry point and global options
    └── _commands.py         # All 21 commands
```

## Key Design Rules

### Connection-per-Operation

Each API call opens its own Unix socket connection, performs the HTTP request, and closes. No connection pooling. Unix sockets are essentially free (no TCP handshake, no TLS). This isolation means streaming, blocking, and detached operations can run simultaneously without interfering.

See [Connection Model](connection-model.md) for details.

### Async Core, Sync Facade

`AsyncContainer` contains all real implementation logic. `Container` is a thin sync wrapper that manages a background event loop thread (`_LoopThread`). Every sync method call is forwarded to the async version via `asyncio.run_coroutine_threadsafe()`.

```
Container.run("echo hello")
    │
    ▼ run_coroutine_threadsafe()
AsyncContainer.run("echo hello")
    │
    ▼ _socket_client.exec_command()
HTTP POST /exec/{id}/start (Unix socket)
```

The `_LoopThread` is a singleton — all sync containers share one background event loop.

### No Cached State

pocket-dock never caches container state. Every `info()` call, every `is_running()` check, every operation hits the engine live. The container might have been killed externally by another process, a resource limit, or an OOM event. Caching would hide these failures.

### HTTP Over Unix Socket

The socket client (`_socket_client.py`) implements raw HTTP/1.1 over Unix domain sockets using Python's `asyncio` stream API. It handles:

- Request serialization (method, path, headers, body)
- Response parsing (status, headers, body)
- Chunked transfer encoding (for streaming)
- Docker stream demultiplexing (8-byte header frames)
- Podman raw stream mode (no framing)

No external HTTP library is used. This keeps the dependency count at zero and gives full control over streaming behavior.

### Three Output Modes

The `run()` method supports three mutually exclusive modes:

| Mode | Parameter | Returns | Use Case |
|------|-----------|---------|----------|
| Blocking | (default) | `ExecResult` | Simple commands |
| Streaming | `stream=True` | `ExecStream` / `AsyncExecStream` | Builds, long scripts |
| Detached | `detach=True` | `Process` / `AsyncProcess` | Background servers |

All three modes share the same exec creation path (`_exec_create` + `_exec_start`) but differ in how they consume the output stream.
