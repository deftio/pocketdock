# CLI Reference

pocket-dock includes a full CLI for managing containers from the terminal.

## Install

```bash
pip install pocket-dock[cli]
```

## Global Options

| Option | Env Var | Description |
|--------|---------|-------------|
| `--socket PATH` | `POCKET_DOCK_SOCKET` | Container engine socket path |
| `--verbose / -v` | — | Enable verbose output |
| `--version` | — | Show version and exit |
| `--help` | — | Show help and exit |

## Project Commands

### `init`

Initialize a `.pocket-dock/` project directory.

```bash
pocket-dock init [PATH]
```

| Option | Description |
|--------|-------------|
| `PATH` | Directory to initialize (default: current directory) |

### `status`

Show project summary and container states.

```bash
pocket-dock status [--json]
```

### `doctor`

Diagnose orphaned containers and stale instance directories.

```bash
pocket-dock doctor [--json]
```

### `logs`

View command history for the project.

```bash
pocket-dock logs [--json] [--history] [--follow] [--limit N]
```

| Option | Description |
|--------|-------------|
| `--history` | Show command history |
| `--follow` | Follow log output |
| `--limit N` | Limit number of entries |

## Container Lifecycle

### `create`

Create a new container.

```bash
pocket-dock create [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--image IMAGE` | Container image (default: `pocket-dock/minimal`) |
| `--name NAME` | Container name (auto-generated if omitted) |
| `--profile PROFILE` | Image profile (`minimal`, `dev`, `agent`, `embedded`) |
| `--mem-limit LIMIT` | Memory limit (e.g., `256m`, `1g`) |
| `--cpu-percent N` | CPU cap as percentage |
| `--persist` | Make container persistent |
| `--device DEVICE` | Device passthrough (can be repeated) |

```bash
pocket-dock create --name my-sandbox --profile dev --mem-limit 512m --persist
```

### `run`

Execute a command inside a container.

```bash
pocket-dock run CONTAINER [OPTIONS] COMMAND...
```

| Option | Description |
|--------|-------------|
| `--stream` | Stream output in real time |
| `--detach` | Run in background |
| `--timeout N` | Command timeout in seconds |
| `--lang LANG` | Language wrapper (e.g., `python`) |

```bash
pocket-dock run my-sandbox echo hello
pocket-dock run my-sandbox --stream make all
pocket-dock run my-sandbox --detach python server.py
pocket-dock run my-sandbox --lang python "print(2 + 2)"
```

### `shell`

Open an interactive shell session.

```bash
pocket-dock shell CONTAINER
```

This passes through to the engine's `exec -it` command (e.g., `docker exec -it CONTAINER /bin/sh`).

### `reboot`

Restart a container.

```bash
pocket-dock reboot CONTAINER [--fresh]
```

| Option | Description |
|--------|-------------|
| `--fresh` | Recreate from scratch (new filesystem) |

### `stop`

Stop a running container without removing it.

```bash
pocket-dock stop CONTAINER
```

### `resume`

Resume a stopped persistent container.

```bash
pocket-dock resume CONTAINER
```

### `shutdown`

Stop and remove a container.

```bash
pocket-dock shutdown CONTAINER [--yes]
```

| Option | Description |
|--------|-------------|
| `--yes / -y` | Skip confirmation prompt |

### `snapshot`

Commit a container's filesystem as a new image.

```bash
pocket-dock snapshot CONTAINER IMAGE_NAME
```

```bash
pocket-dock snapshot my-sandbox my-sandbox:v1
```

### `prune`

Remove all stopped pocket-dock containers.

```bash
pocket-dock prune [--yes] [--project PROJECT]
```

| Option | Description |
|--------|-------------|
| `--yes / -y` | Skip confirmation prompt |
| `--project PROJECT` | Only prune containers for this project |

## Information Commands

### `list`

List all pocket-dock managed containers.

```bash
pocket-dock list [--json] [--project PROJECT]
```

```bash
pocket-dock list
pocket-dock list --json
pocket-dock list --project my-app
```

### `info`

Show detailed information about a container.

```bash
pocket-dock info CONTAINER [--json]
```

## File Operations

### `push`

Copy a file or directory from the host into a container.

```bash
pocket-dock push CONTAINER SRC DEST
```

```bash
pocket-dock push my-sandbox ./src/ /home/sandbox/src/
```

### `pull`

Copy a file or directory from a container to the host.

```bash
pocket-dock pull CONTAINER SRC DEST
```

```bash
pocket-dock pull my-sandbox /home/sandbox/output.csv ./output.csv
```

## Image Profile Commands

### `profiles`

List available image profiles.

```bash
pocket-dock profiles [--json]
```

### `build`

Build profile images from Dockerfiles.

```bash
pocket-dock build [PROFILE]
```

```bash
pocket-dock build           # Build all profiles
pocket-dock build minimal   # Build a specific profile
```

### `export`

Save images to a tar/tar.gz file for transfer.

```bash
pocket-dock export [OPTIONS] -o OUTPUT
```

| Option | Description |
|--------|-------------|
| `--all` | Export all profile images |
| `-o / --output FILE` | Output file path |

```bash
pocket-dock export --all -o images.tar.gz
```

### `import`

Load images from a tar/tar.gz file.

```bash
pocket-dock import FILE
```

```bash
pocket-dock import images.tar.gz
```

## JSON Output

Read commands support `--json` for machine-readable output:

```bash
pocket-dock list --json
pocket-dock info my-sandbox --json
pocket-dock doctor --json
pocket-dock status --json
pocket-dock logs --json
pocket-dock profiles --json
```
