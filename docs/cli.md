# CLI Reference

pocketdock includes a full CLI for managing containers from the terminal.

## Install

```bash
pip install pocketdock[cli]
```

## Global Options

| Option | Env Var | Description |
|--------|---------|-------------|
| `--socket PATH` | `POCKETDOCK_SOCKET` | Container engine socket path |
| `--verbose / -v` | — | Enable verbose output |
| `--version` | — | Show version and exit |
| `--help` | — | Show help and exit |

## Project Commands

### `init`

Initialize a `.pocketdock/` project directory.

```bash
pocketdock init [PATH]
```

| Option | Description |
|--------|-------------|
| `PATH` | Directory to initialize (default: current directory) |

### `status`

Show project summary and container states.

```bash
pocketdock status [--json]
```

### `doctor`

Diagnose orphaned containers and stale instance directories.

```bash
pocketdock doctor [--json]
```

### `logs`

View command history for the project.

```bash
pocketdock logs [--json] [--history] [--follow] [--limit N]
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
pocketdock create [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--image IMAGE` | Container image (default: `pocketdock/minimal`) |
| `--name NAME` | Container name (auto-generated if omitted) |
| `--profile PROFILE` | Image profile (`minimal`, `dev`, `agent`, `embedded`) |
| `--mem-limit LIMIT` | Memory limit (e.g., `256m`, `1g`) |
| `--cpu-percent N` | CPU cap as percentage |
| `--persist` | Make container persistent |
| `--device DEVICE` | Device passthrough (can be repeated) |

```bash
pocketdock create --name my-sandbox --profile dev --mem-limit 512m --persist
```

### `run`

Execute a command inside a container.

```bash
pocketdock run CONTAINER [OPTIONS] COMMAND...
```

| Option | Description |
|--------|-------------|
| `--stream` | Stream output in real time |
| `--detach` | Run in background |
| `--timeout N` | Command timeout in seconds |
| `--lang LANG` | Language wrapper (e.g., `python`) |

```bash
pocketdock run my-sandbox echo hello
pocketdock run my-sandbox --stream make all
pocketdock run my-sandbox --detach python server.py
pocketdock run my-sandbox --lang python "print(2 + 2)"
```

### `shell`

Open an interactive shell session.

```bash
pocketdock shell CONTAINER
```

This passes through to the engine's `exec -it` command (e.g., `docker exec -it CONTAINER /bin/sh`).

### `reboot`

Restart a container.

```bash
pocketdock reboot CONTAINER [--fresh]
```

| Option | Description |
|--------|-------------|
| `--fresh` | Recreate from scratch (new filesystem) |

### `stop`

Stop a running container without removing it.

```bash
pocketdock stop CONTAINER
```

### `resume`

Resume a stopped persistent container.

```bash
pocketdock resume CONTAINER
```

### `shutdown`

Stop and remove a container.

```bash
pocketdock shutdown CONTAINER [--yes]
```

| Option | Description |
|--------|-------------|
| `--yes / -y` | Skip confirmation prompt |

### `snapshot`

Commit a container's filesystem as a new image.

```bash
pocketdock snapshot CONTAINER IMAGE_NAME
```

```bash
pocketdock snapshot my-sandbox my-sandbox:v1
```

### `prune`

Remove all stopped pocketdock containers.

```bash
pocketdock prune [--yes] [--project PROJECT]
```

| Option | Description |
|--------|-------------|
| `--yes / -y` | Skip confirmation prompt |
| `--project PROJECT` | Only prune containers for this project |

## Information Commands

### `list`

List all pocketdock managed containers.

```bash
pocketdock list [--json] [--project PROJECT]
```

```bash
pocketdock list
pocketdock list --json
pocketdock list --project my-app
```

### `info`

Show detailed information about a container.

```bash
pocketdock info CONTAINER [--json]
```

## File Operations

### `push`

Copy a file or directory from the host into a container.

```bash
pocketdock push CONTAINER SRC DEST
```

```bash
pocketdock push my-sandbox ./src/ /home/sandbox/src/
```

### `pull`

Copy a file or directory from a container to the host.

```bash
pocketdock pull CONTAINER SRC DEST
```

```bash
pocketdock pull my-sandbox /home/sandbox/output.csv ./output.csv
```

## Image Profile Commands

### `profiles`

List available image profiles.

```bash
pocketdock profiles [--json]
```

### `build`

Build profile images from Dockerfiles.

```bash
pocketdock build [PROFILE]
```

```bash
pocketdock build           # Build all profiles
pocketdock build minimal   # Build a specific profile
```

### `export`

Save images to a tar/tar.gz file for transfer.

```bash
pocketdock export [OPTIONS] -o OUTPUT
```

| Option | Description |
|--------|-------------|
| `--all` | Export all profile images |
| `-o / --output FILE` | Output file path |

```bash
pocketdock export --all -o images.tar.gz
```

### `import`

Load images from a tar/tar.gz file.

```bash
pocketdock import FILE
```

```bash
pocketdock import images.tar.gz
```

## JSON Output

Read commands support `--json` for machine-readable output:

```bash
pocketdock list --json
pocketdock info my-sandbox --json
pocketdock doctor --json
pocketdock status --json
pocketdock logs --json
pocketdock profiles --json
```
