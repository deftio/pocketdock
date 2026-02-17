# Error Reference

All exceptions inherit from `PocketDockError` and can be imported from `pocketdock`.

## Hierarchy

```
PocketDockError
├── SocketError
│   ├── SocketConnectionError
│   ├── SocketCommunicationError
│   └── PodmanNotRunning
├── ContainerError
│   ├── ContainerNotFound
│   ├── ContainerNotRunning
│   └── ContainerGone
├── ImageNotFound
├── SessionClosed
└── ProjectNotInitialized
```

## Base Exception

### `PocketDockError`

Base exception for all pocketdock errors. Catch this to handle any pocketdock error:

```python
from pocketdock import PocketDockError

try:
    c = create_new_container()
except PocketDockError as e:
    print(f"pocketdock error: {e}")
```

## Socket Errors

Raised when there are issues connecting to or communicating with the container engine.

### `SocketError`

Base class for all socket-related errors.

### `SocketConnectionError`

Cannot connect to the container engine socket.

| Attribute | Type | Description |
|-----------|------|-------------|
| `socket_path` | `str` | Path to the socket that failed |
| `detail` | `str` | Additional error details |

**When raised:** The socket file doesn't exist, permission denied, or the engine isn't running.

```python
from pocketdock import SocketConnectionError

try:
    c = create_new_container()
except SocketConnectionError as e:
    print(f"Can't connect to {e.socket_path}: {e.detail}")
```

### `SocketCommunicationError`

Error during communication over the socket.

| Attribute | Type | Description |
|-----------|------|-------------|
| `detail` | `str` | Error details |

**When raised:** Unexpected response, malformed data, or connection dropped during an operation.

### `PodmanNotRunning`

No container engine socket found.

**When raised:** Auto-detection checked all known socket paths and none were available.

The error message includes a platform-specific hint:

- **Linux:** `Try: systemctl --user start podman.socket`
- **macOS:** `Try: podman machine start  OR  open Docker Desktop`

## Container Errors

Raised when there are issues with a specific container.

### `ContainerError`

Base class for container-related errors.

| Attribute | Type | Description |
|-----------|------|-------------|
| `container_id` | `str` | Container ID or name |
| `detail` | `str` | Additional error details |

### `ContainerNotFound`

Container does not exist.

| Attribute | Type | Description |
|-----------|------|-------------|
| `container_id` | `str` | Container ID or name |

**When raised:** The engine returned a 404 for the container ID. The container was never created, or it was already removed.

```python
from pocketdock import ContainerNotFound

try:
    c = resume_container("nonexistent")
except ContainerNotFound as e:
    print(f"Container not found: {e.container_id}")
```

### `ContainerNotRunning`

Container exists but is not running.

| Attribute | Type | Description |
|-----------|------|-------------|
| `container_id` | `str` | Container ID or name |

**When raised:** An operation that requires a running container (e.g., `run()`, `session()`) was called on a stopped container.

### `ContainerGone`

Container was removed externally.

| Attribute | Type | Description |
|-----------|------|-------------|
| `container_id` | `str` | Container ID or name |

**When raised:** The container existed when pocketdock last checked, but it's gone now. Likely removed by another process or the engine.

## Image Errors

### `ImageNotFound`

Requested image does not exist locally.

| Attribute | Type | Description |
|-----------|------|-------------|
| `image` | `str` | Image tag |

**When raised:** `create_new_container()` was called with an image that hasn't been built or pulled.

```python
from pocketdock import ImageNotFound

try:
    c = create_new_container(image="nonexistent:latest")
except ImageNotFound as e:
    print(f"Image not found: {e.image}")
```

## Session Errors

### `SessionClosed`

Operation attempted on a closed session.

**When raised:** `send()`, `send_and_wait()`, or `read()` was called after `close()`.

```python
from pocketdock import SessionClosed

sess = c.session()
sess.close()
try:
    sess.send("echo hello")
except SessionClosed:
    print("Session is closed")
```

## Project Errors

### `ProjectNotInitialized`

Operation requires a project directory that doesn't exist.

**When raised:** `doctor()` or project-related operations were called outside a `.pocketdock/` project directory.

```python
from pocketdock import ProjectNotInitialized

try:
    report = doctor()
except ProjectNotInitialized:
    print("Run init_project() first")
```
