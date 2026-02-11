# Persistence

By default, containers are ephemeral — they are removed when `shutdown()` is called or the context manager exits. Persistence features let you stop, resume, snapshot, and manage containers across sessions.

## Persistent Containers

Create a container that survives `shutdown()`:

```python
from pocket_dock import create_new_container

c = create_new_container(persist=True, name="my-sandbox")
c.run("echo setup done")
c.shutdown()  # Stops the container, but does NOT remove it
```

## Resume

Resume a stopped persistent container by name:

```python
from pocket_dock import resume_container

c = resume_container("my-sandbox")
result = c.run("echo I'm back")
print(result.stdout)  # "I'm back\n"
```

The container's filesystem state is preserved from the previous session.

## List Containers

List all pocket-dock managed containers (running and stopped):

```python
from pocket_dock import list_containers

containers = list_containers()
for item in containers:
    print(f"{item.name}: {item.status} (persist={item.persist})")
```

Each item is a `ContainerListItem` with:

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Container ID |
| `name` | `str` | Container name |
| `status` | `str` | `"running"` or `"exited"` |
| `image` | `str` | Image tag |
| `created_at` | `str` | ISO creation timestamp |
| `persist` | `bool` | Whether the container is persistent |
| `project` | `str` | Associated project name |

Filter by project:

```python
containers = list_containers(project="my-project")
```

## Stop

Stop a running container without removing it:

```python
from pocket_dock import stop_container

stop_container("my-sandbox")
```

## Destroy

Permanently remove a container regardless of its persist setting:

```python
from pocket_dock import destroy_container

destroy_container("my-sandbox")
```

If the container has an associated instance directory (from project management), it is also cleaned up.

## Prune

Remove all stopped pocket-dock managed containers:

```python
from pocket_dock import prune

count = prune()
print(f"Removed {count} containers")
```

Filter by project:

```python
count = prune(project="my-project")
```

## Snapshot

Commit the container's current filesystem as a reusable image:

```python
c = create_new_container(persist=True, name="my-sandbox")
c.run("pip install requests")
image_id = c.snapshot("my-sandbox:with-requests")
```

Create new containers from the snapshot:

```python
c2 = create_new_container(image="my-sandbox:with-requests")
```

## Volumes

Mount host directories for data that should persist independently of the container:

```python
c = create_new_container(
    volumes={"/host/data": "/container/data"}
)
```

Volume changes are written directly to the host filesystem and survive container removal.

## Socket Path

All persistence functions accept an optional `socket_path` parameter to target a specific engine:

```python
containers = list_containers(socket_path="/path/to/docker.sock")
```
