# Types Reference

All types are frozen dataclasses importable from `pocketdock`.

## ExecResult

Result of a command execution.

```python
from pocketdock import ExecResult
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `exit_code` | `int` | — | Process exit code |
| `stdout` | `str` | `""` | Standard output |
| `stderr` | `str` | `""` | Standard error |
| `duration_ms` | `float` | `0.0` | Execution time in milliseconds |
| `timed_out` | `bool` | `False` | Whether the command timed out |
| `truncated` | `bool` | `False` | Whether output was truncated |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `ok` | `bool` | `True` if `exit_code == 0` and not `timed_out` |

```python
result = c.run("echo hello")
result.ok           # True
result.exit_code    # 0
result.stdout       # "hello\n"
result.duration_ms  # 47.2
```

## ContainerInfo

Live snapshot of a container's state.

```python
info = c.info()
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | — | Container ID |
| `name` | `str` | — | Container name |
| `status` | `str` | — | `"running"`, `"exited"`, etc. |
| `image` | `str` | — | Image tag |
| `created_at` | `datetime.datetime` | — | Creation timestamp |
| `started_at` | `datetime.datetime \| None` | `None` | Start timestamp |
| `uptime` | `datetime.timedelta \| None` | `None` | Time since started |
| `memory_usage` | `str` | `""` | Human-readable memory usage (e.g., `"42.1 MB"`) |
| `memory_limit` | `str` | `""` | Human-readable memory limit (e.g., `"256 MB"`) |
| `memory_percent` | `float` | `0.0` | Memory usage as percentage |
| `cpu_percent` | `float` | `0.0` | CPU usage as percentage |
| `pids` | `int` | `0` | Number of running processes |
| `network` | `bool` | `False` | Whether networking is enabled |
| `ip_address` | `str` | `""` | Container IP address |
| `ports` | `dict[int, int]` | `{}` | Host-to-container port mappings |
| `processes` | `tuple[dict[str, str], ...]` | `()` | Running processes |

## ContainerListItem

Summary of a container from `list_containers()`.

```python
from pocketdock import list_containers

items = list_containers()
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | — | Container ID |
| `name` | `str` | — | Container name |
| `status` | `str` | — | `"running"` or `"exited"` |
| `image` | `str` | — | Image tag |
| `created_at` | `str` | — | ISO creation timestamp |
| `persist` | `bool` | — | Whether container is persistent |
| `project` | `str` | `""` | Associated project name |

## StreamChunk

A chunk of output from a streaming command.

```python
for chunk in c.run("make all", stream=True):
    print(f"[{chunk.stream}] {chunk.data}", end="")
```

| Field | Type | Description |
|-------|------|-------------|
| `stream` | `str` | `"stdout"` or `"stderr"` |
| `data` | `str` | Text content |

## BufferSnapshot

Snapshot of a detached process's ring buffer.

```python
proc = c.run("python server.py", detach=True)
output = proc.peek()
```

| Field | Type | Description |
|-------|------|-------------|
| `stdout` | `str` | Buffered stdout content |
| `stderr` | `str` | Buffered stderr content |

## DoctorReport

Result of `doctor()` health check.

```python
from pocketdock import doctor

report = doctor()
```

| Field | Type | Description |
|-------|------|-------------|
| `orphaned_containers` | `tuple[str, ...]` | Container names without matching instance dirs |
| `stale_instance_dirs` | `tuple[str, ...]` | Instance dir names without matching containers |
| `healthy` | `int` | Count of healthy container-dir pairs |

## ProfileInfo

Metadata about an image profile.

```python
from pocketdock import resolve_profile

info = resolve_profile("minimal-python")
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Profile name |
| `image_tag` | `str` | Docker/Podman image tag |
| `dockerfile_dir` | `str` | Path to Dockerfile directory |
| `network_default` | `bool` | Default network setting |
| `description` | `str` | Human-readable description |
| `size_estimate` | `str` | Approximate image size |
