# API Reference

## Module: `pocketdock`

Sync API. All container operations are blocking.

### Container Creation

#### `create_new_container(**kwargs) -> Container`

Create and start a new container.

```python
from pocketdock import create_new_container

c = create_new_container(
    image="pocketdock/minimal-python",  # Container image tag
    name=None,                     # Auto-generated if None
    timeout=30,                    # Default exec timeout (seconds)
    mem_limit=None,                # Memory limit ("256m", "1g")
    cpu_percent=None,              # CPU cap (0-100)
    persist=False,                 # Survive shutdown()
    volumes=None,                  # {"/host": "/container"}
    project=None,                  # Project name
    profile=None,                  # Image profile name
    devices=None,                  # ["/dev/ttyUSB0"]
    ports=None,                    # {8080: 80}
)
```

All parameters are keyword-only.

### Container Management

#### `resume_container(name, *, socket_path=None, timeout=30) -> Container`

Resume a stopped persistent container by name.

#### `list_containers(*, socket_path=None, project=None) -> list[ContainerListItem]`

List all pocketdock managed containers (running and stopped).

#### `stop_container(name, *, socket_path=None) -> None`

Stop a running container without removing it.

#### `destroy_container(name, *, socket_path=None) -> None`

Permanently remove a container.

#### `prune(*, socket_path=None, project=None) -> int`

Remove all stopped pocketdock containers. Returns the count of removed containers.

#### `doctor(*, project_root=None, socket_path=None) -> DoctorReport`

Cross-reference local instance directories with the container engine.

### Project Management

#### `find_project_root(start=None) -> Path | None`

Walk up from `start` (default: cwd) looking for `.pocketdock/pocketdock.yaml`. Returns the project root directory, or `None`.

#### `init_project(path=None, *, project_name=None) -> Path`

Create a `.pocketdock/pocketdock.yaml` file. Returns the project root path.

### Profile Management

#### `resolve_profile(name) -> ProfileInfo`

Look up a profile by name. Returns a `ProfileInfo` dataclass.

#### `list_profiles() -> list[ProfileInfo]`

Return all available profiles.

### Version

#### `get_version() -> str`

Return the package version string.

#### `__version__: str`

Package version (e.g., `"1.2.3"`).

---

## Class: `Container`

Sync container handle. Wraps `AsyncContainer` with a background event loop.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `container_id` | `str` | Full container ID |
| `socket_path` | `str` | Engine socket path |
| `name` | `str` | Container name |
| `persist` | `bool` | Persistent container |
| `project` | `str` | Project name |
| `data_path` | `str` | Instance data directory |

### Methods

#### `run(command, *, stream=False, detach=False, timeout=None, max_output=10_485_760, lang=None)`

Execute a command inside the container.

Returns:

- **Default**: `ExecResult` — blocking execution
- **`stream=True`**: `ExecStream` — sync iterator of `StreamChunk`
- **`detach=True`**: `Process` — background process handle

#### `info() -> ContainerInfo`

Live container snapshot with status, resources, and processes.

#### `reboot(*, fresh=False) -> None`

Restart the container. `fresh=True` recreates from scratch.

#### `write_file(path, content) -> None`

Write text (`str`) or binary (`bytes`) content to a file in the container.

#### `read_file(path) -> bytes`

Read file contents from the container.

#### `list_files(path="/home/sandbox") -> list[str]`

List a directory inside the container.

#### `push(src, dest) -> None`

Copy a file or directory from the host into the container.

#### `pull(src, dest) -> None`

Copy a file or directory from the container to the host.

#### `session() -> Session`

Open a persistent shell session.

#### `snapshot(image_name) -> str`

Commit the container's filesystem as a new image. Returns the image ID.

#### `shutdown(*, force=False) -> None`

Stop and remove the container. For persistent containers, stop only.

#### `on_stdout(fn) -> None`

Register a stdout callback: `fn(container, data: str)`.

#### `on_stderr(fn) -> None`

Register a stderr callback: `fn(container, data: str)`.

#### `on_exit(fn) -> None`

Register an exit callback: `fn(container, exit_code: int)`.

---

## Class: `Session`

Persistent shell session (sync). Alias for `SyncSession`.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `id` | `str` | Exec instance ID |

### Methods

#### `send(command) -> None`

Fire-and-forget command.

#### `send_and_wait(command, *, timeout=None) -> ExecResult`

Send command and wait for result.

#### `read() -> str`

Drain accumulated output.

#### `on_output(fn) -> None`

Register output callback: `fn(data: str)`.

#### `close() -> None`

Close the session.

---

## Class: `ExecStream`

Sync iterator of `StreamChunk` objects. Alias for `SyncExecStream`.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `result` | `ExecResult` | Available after iteration completes |

### Usage

```python
for chunk in c.run("make all", stream=True):
    print(chunk.data, end="")
```

---

## Class: `Process`

Detached process handle (sync). Alias for `SyncProcess`.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `id` | `str` | Exec instance ID |
| `buffer_size` | `int` | Current bytes in buffer |
| `buffer_overflow` | `bool` | True if data evicted |

### Methods

#### `is_running() -> bool`

Check if the process is still running.

#### `kill(signal=15) -> None`

Send a signal to the process.

#### `wait(timeout=None) -> ExecResult`

Wait for process completion.

#### `read() -> BufferSnapshot`

Consume and clear the buffer.

#### `peek() -> BufferSnapshot`

Read without consuming.

---

## Module: `pocketdock.async_`

Async API. All methods are coroutines (use `await`).

### `create_new_container(**kwargs) -> AsyncContainer`

Same parameters as the sync version. Returns an `AsyncContainer`.

```python
async with await create_new_container() as c:
    result = await c.run("echo hello")
```

### Async Functions

All management functions mirror the sync API:

- `resume_container(name, ...) -> AsyncContainer`
- `list_containers(...) -> list[ContainerListItem]`
- `stop_container(name, ...) -> None`
- `destroy_container(name, ...) -> None`
- `prune(...) -> int`
- `doctor(...) -> DoctorReport`

### Class: `AsyncContainer`

Same interface as `Container` but all methods are coroutines.

### Class: `AsyncSession`

Same interface as `Session` but `send()`, `send_and_wait()`, and `close()` are coroutines.

### Class: `AsyncExecStream`

Async iterator of `StreamChunk`:

```python
async for chunk in await c.run("make all", stream=True):
    print(chunk.data, end="")
```

### Class: `AsyncProcess`

Same as `Process` but `is_running()`, `kill()`, and `wait()` are coroutines.
