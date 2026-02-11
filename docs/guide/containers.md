# Creating Containers

## Basic Usage

```python
from pocketdock import create_new_container

c = create_new_container()
result = c.run("echo hello")
c.shutdown()
```

With a context manager:

```python
with create_new_container() as c:
    result = c.run("echo hello")
# Automatic cleanup
```

## Parameters

`create_new_container()` accepts the following keyword-only arguments:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `image` | `str` | `"pocketdock/minimal"` | Container image tag |
| `name` | `str \| None` | `None` | Container name (auto-generated as `pd-{hex}` if `None`) |
| `timeout` | `int` | `30` | Default exec timeout in seconds |
| `mem_limit` | `str \| None` | `None` | Memory limit (e.g., `"256m"`, `"1g"`) |
| `cpu_percent` | `int \| None` | `None` | CPU cap as percentage (e.g., `50`) |
| `persist` | `bool` | `False` | If `True`, `shutdown()` stops but doesn't remove |
| `volumes` | `dict[str, str] \| None` | `None` | Host-to-container mounts |
| `project` | `str \| None` | `None` | Project name (auto-detected from `.pocketdock/`) |
| `profile` | `str \| None` | `None` | Image profile name (`"minimal"`, `"dev"`, `"agent"`, `"embedded"`) |
| `devices` | `list[str] \| None` | `None` | Host devices to passthrough (e.g., `["/dev/ttyUSB0"]`) |

```python
c = create_new_container(
    image="pocketdock/dev",
    name="my-sandbox",
    timeout=60,
    mem_limit="512m",
    cpu_percent=75,
    persist=True,
    volumes={"/host/data": "/container/data"},
)
```

## Container Properties

| Property | Type | Description |
|----------|------|-------------|
| `container_id` | `str` | Full container ID hex string |
| `socket_path` | `str` | Path to the engine Unix socket |
| `name` | `str` | Human-readable container name |
| `persist` | `bool` | Whether the container survives `shutdown()` |
| `project` | `str` | Associated project name (empty if none) |
| `data_path` | `str` | Instance data directory path (empty if none) |

## Container Info

Get a live snapshot of the container's state:

```python
info = c.info()

info.status          # "running"
info.image           # "pocketdock/minimal"
info.memory_usage    # "42.1 MB"
info.memory_limit    # "256 MB"
info.memory_percent  # 16.4
info.cpu_percent     # 3.2
info.pids            # 2
info.network         # True
info.ip_address      # "172.17.0.2"
info.uptime          # datetime.timedelta(seconds=45)
info.processes       # tuple of process dicts
```

See [Types > ContainerInfo](../reference/types.md#containerinfo) for all 15 fields.

## Resource Limits

Set memory and CPU limits at creation time:

```python
# Memory limit: 256MB
c = create_new_container(mem_limit="256m")

# CPU limit: 50% of one core
c = create_new_container(cpu_percent=50)

# Both
c = create_new_container(mem_limit="1g", cpu_percent=75)
```

Memory format: `"256m"`, `"512m"`, `"1g"`, `"2g"`, etc.

## Reboot

Restart the container in place (preserves the filesystem):

```python
c.reboot()
```

Recreate from scratch with the same configuration (fresh filesystem):

```python
c.reboot(fresh=True)
```

## Snapshot

Commit the container's current filesystem as a new image:

```python
image_id = c.snapshot("my-image:v1")
```

The image can be used to create new containers:

```python
c2 = create_new_container(image="my-image:v1")
```

## Shutdown

Stop and remove the container:

```python
c.shutdown()           # Graceful stop (SIGTERM, then SIGKILL after timeout)
c.shutdown(force=True) # Immediate SIGKILL
```

For persistent containers (`persist=True`), `shutdown()` only stops — it doesn't remove:

```python
c = create_new_container(persist=True, name="my-sandbox")
c.shutdown()  # Stops, but container can be resumed later
```

See [Persistence](persistence.md) for resume/destroy operations.

## Volumes

Mount host directories into the container:

```python
c = create_new_container(
    volumes={
        "/host/project/src": "/home/sandbox/src",
        "/host/data": "/home/sandbox/data",
    }
)
```

Volume mounts are read-write. The host path is the dict key, the container path is the value.
