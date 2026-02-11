# Projects

pocket-dock projects group containers with a shared configuration directory (`.pocket-dock/`) that lives next to your code.

## Initialize a Project

```python
from pocket_dock import init_project

project_root = init_project()  # Creates .pocket-dock/ in the current directory
```

Or specify a path:

```python
project_root = init_project("/path/to/my-project")
```

With a custom project name:

```python
project_root = init_project(project_name="my-app")
```

This creates:

```
my-project/
├── .pocket-dock/
│   └── pocket-dock.yaml
└── ... (your code)
```

## Find Project Root

Walk up from a directory to find the nearest `.pocket-dock/pocket-dock.yaml`:

```python
from pocket_dock import find_project_root

root = find_project_root()  # Starts from cwd
root = find_project_root("/some/nested/dir")
```

Returns `None` if no project is found.

## Project Configuration

The `pocket-dock.yaml` file configures project defaults:

```yaml
project_name: my-app
default_profile: minimal
default_persist: false
auto_log: true
max_log_size: 10MB
max_logs_per_instance: 100
retention_days: 30
socket: null
log_level: info
```

See [Configuration](../reference/configuration.md) for full details.

## Associate Containers with a Project

Pass the `project` parameter when creating containers:

```python
c = create_new_container(project="my-app", persist=True)
```

If you're inside a project directory, the project is auto-detected:

```python
# Inside a directory with .pocket-dock/pocket-dock.yaml
c = create_new_container(persist=True)
# project is auto-detected from the nearest .pocket-dock/
```

## Instance Directories

Each persistent container in a project gets its own instance directory:

```
.pocket-dock/
├── pocket-dock.yaml
└── instances/
    └── my-sandbox/
        ├── instance.toml    # Container metadata
        ├── history.jsonl    # Command history
        └── logs/            # Session and detach logs
```

### Instance Metadata

`instance.toml` contains container metadata:

```toml
container_id = "abc123..."
name = "my-sandbox"
image = "pocket-dock/minimal"
project = "my-app"
created_at = "2026-01-15T10:30:00"
persist = true
mem_limit = "256m"
cpu_percent = 50
```

### Command History

`history.jsonl` logs every `run()` call with timestamps, commands, exit codes, and durations.

## Doctor

Diagnose project health by cross-referencing local instance directories with the container engine:

```python
from pocket_dock import doctor

report = doctor()
report.orphaned_containers    # Containers with no instance dir
report.stale_instance_dirs    # Instance dirs with no container
report.healthy                # Count of healthy container-dir pairs
```

The `DoctorReport` fields:

| Field | Type | Description |
|-------|------|-------------|
| `orphaned_containers` | `tuple[str, ...]` | Container names without matching instance dirs |
| `stale_instance_dirs` | `tuple[str, ...]` | Instance dir names without matching containers |
| `healthy` | `int` | Count of healthy pairs |

### ProjectNotInitialized

If `doctor()` is called outside a project directory, it raises `ProjectNotInitialized`:

```python
from pocket_dock import ProjectNotInitialized

try:
    report = doctor()
except ProjectNotInitialized:
    print("Run init_project() first")
```
