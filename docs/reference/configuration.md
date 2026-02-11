# Configuration

pocketdock uses a layered configuration system with project-level and environment-level settings.

## pocketdock.yaml

The primary configuration file, located at `.pocketdock/pocketdock.yaml` in your project root:

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

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `project_name` | `str` | `""` | Human-readable project name |
| `default_profile` | `str` | `"minimal"` | Default image profile for `create_new_container()` |
| `default_persist` | `bool` | `false` | Default persist setting for new containers |
| `auto_log` | `bool` | `true` | Automatically log `run()` results and session I/O |
| `max_log_size` | `str` | `"10MB"` | Maximum size per log file |
| `max_logs_per_instance` | `int` | `100` | Maximum log files per instance |
| `retention_days` | `int` | `30` | Days to retain log files |
| `socket` | `str \| null` | `null` | Container engine socket path (overrides auto-detection) |
| `log_level` | `str` | `"info"` | Log level (`debug`, `info`, `warning`, `error`) |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `POCKETDOCK_SOCKET` | Container engine socket path (overrides config and auto-detection) |

## Config Precedence

Configuration is resolved in this order (highest priority first):

1. **Explicit parameters** — `socket_path` passed to functions
2. **Environment variables** — `POCKETDOCK_SOCKET`
3. **Project config** — `.pocketdock/pocketdock.yaml`
4. **Auto-detection** — built-in socket discovery

## Socket Auto-Detection

If no socket is specified, pocketdock searches in this order:

1. `POCKETDOCK_SOCKET` environment variable
2. Podman rootless: `$XDG_RUNTIME_DIR/podman/podman.sock`
3. Podman system: `/run/podman/podman.sock`
4. Docker: `/var/run/docker.sock`

## Loading Config Programmatically

```python
from pocketdock._config import load_config, PocketDockConfig

config = load_config()  # Auto-discovers project root
config = load_config(project_root=Path("/path/to/project"))

config.project_name      # "my-app"
config.default_profile   # "minimal"
config.auto_log          # True
```

### PocketDockConfig Fields

| Field | Type | Default |
|-------|------|---------|
| `project_name` | `str` | `""` |
| `default_profile` | `str` | `"minimal"` |
| `default_persist` | `bool` | `False` |
| `auto_log` | `bool` | `True` |
| `max_log_size` | `str` | `"10MB"` |
| `max_logs_per_instance` | `int` | `100` |
| `retention_days` | `int` | `30` |
| `socket` | `str \| None` | `None` |
| `log_level` | `str` | `"info"` |

## instance.toml

Each persistent container in a project gets an `instance.toml` metadata file:

```
.pocketdock/instances/my-sandbox/instance.toml
```

```toml
container_id = "abc123def456..."
name = "my-sandbox"
image = "pocketdock/minimal"
project = "my-app"
created_at = "2026-01-15T10:30:00"
persist = true
mem_limit = "256m"
cpu_percent = 50
```

This file is managed automatically by pocketdock. It tracks container provenance and configuration for resumption and health checks.

## Project Directory Structure

```
my-project/
├── .pocketdock/
│   ├── pocketdock.yaml          # Project configuration
│   └── instances/
│       └── my-sandbox/
│           ├── instance.toml     # Container metadata
│           ├── history.jsonl     # Command history
│           └── logs/             # Session and detach logs
└── ... (your code)
```
