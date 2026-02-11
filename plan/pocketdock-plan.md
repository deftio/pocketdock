# pocketdock

> **This document lives at `plan/spec.md` in the repo.** It is the architecture and design spec, not the README. The README is a concise quickstart for users. This spec is the complete reference for contributors and the authoritative source of truth for architectural decisions. Docs, examples, and code are generated from decisions made here.

**Portable, offline-first container sandboxes for LLM agents and dev workflows.**

One `Container` class. Podman-first, Docker-compatible. Python SDK + CLI. Zero external dependencies. Zero API keys. Zero cloud.

---

## Problem

You're building something that needs to execute code in isolation — an LLM agent, a code evaluation pipeline, an embedded dev sandbox. Your options today are:

- **Managed platforms** (E2B, Daytona): Fast and polished, but require API keys, cloud accounts, paid tiers, and internet access.
- **Roll your own**: You end up rewriting the same ~200 lines of container SDK glue code every time — container lifecycle, exec, stream demuxing, cleanup, error handling.
- **Open Interpreter**: Interactive assistant, not a sandbox. Runs code on your host.

pocketdock fills the gap: a thin, reusable library that talks directly to your container engine over its Unix socket, ships with pre-baked images you build once and keep locally, and works entirely offline after initial setup.

---

## Goals

1. **Offline-first.** After the initial image build, everything works without internet. No image pulls at runtime. No API calls. No telemetry.

2. **Zero external dependencies.** The SDK talks raw HTTP over Unix sockets to the container engine's REST API. No `docker-py`. No `podman-py`. The only dependency is a container engine on your system.

3. **Podman-first, Docker-compatible.** Podman is the recommended engine (rootless, daemonless, better security). Docker works identically — same REST API, same socket protocol.

4. **Python SDK + CLI.** Zero-dependency Python SDK (stdlib-only socket client) and a polished CLI. Same codebase, same install.

5. **Pre-baked image profiles.** Dockerfiles for common use cases — Python, dev tools, C/C++ embedded, agent workloads. Built once locally, reused forever.

6. **A real CLI.** Not an afterthought. Beautiful help output, destructive-action confirmations, built-in structured logging, sensible defaults.

7. **Project-rooted organization.** Containers are grouped into projects via labels. Instance data (logs, history, working files) lives in `.pocketdock/` in the project directory, not in a global registry.

---

## Non-Goals

- Not a container orchestrator. No Kubernetes. No Swarm. No service mesh. No scaling, load balancing, or service discovery.
- Not a security-hardened sandbox for adversarial inputs. Container-level isolation (shared kernel). For truly untrusted code, use gVisor/Firecracker on top.
- Not a process supervisor. pocketdock manages container **lifecycle** (create, run, stop, resume, destroy) but not **restart policies** or **boot-time startup**. If you want a container to survive host reboot, use `pocketdock resume` manually or write a systemd unit. pocketdock doesn't manage system services.
- No Windows container support (Linux containers on any host OS via Docker Desktop / Podman Machine is fine).

### Long-running containers

If you `pocketdock create --persist --port 8080:8080` and run a server inside, that container stays up until you stop it. It's not tied to your terminal session — closing your shell doesn't kill it. This is supported and expected.

**Management tools:**

- `pocketdock list` — show all containers. `--running` for active only, `--all` for including stopped.
- `pocketdock info CONTAINER` — status, uptime, resource usage, last exec activity.
- `pocketdock logs CONTAINER --follow` — tail output in real-time.
- `pocketdock stop CONTAINER` / `pocketdock stop --all` — bring down one or all containers.
- `pocketdock resume CONTAINER` — bring a stopped persistent container back up.
- `pocketdock doctor` — find orphaned containers, stale metadata, port conflicts.

**Idle timeout (optional config):**

```yaml
# .pocketdock/pocketdock.yaml
containers:
  idle_timeout: "4h"   # auto-stop containers with no exec activity for 4 hours
```

This is auto-*stop*, not auto-*restart*. Prevents forgotten containers from consuming resources indefinitely. Disabled by default. Checked by `pocketdock doctor` or a lightweight background poll.

**What pocketdock does NOT do:** auto-restart on crash, health checks, start on boot, restart policies. That's process supervision. If you need it, use systemd:

```bash
# Generate a systemd user unit for a persistent container
pocketdock systemd CONTAINER > ~/.config/systemd/user/pocketdock-myapp.service
systemctl --user enable --now pocketdock-myapp
```

`pocketdock systemd` generates the unit file. The user installs and manages it. pocketdock doesn't touch systemd directly.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Your code / LLM agent / CLI                                    │
│                                                                  │
│   # Sync (default)                  # Async                     │
│   c = create_new_container()        c = await create_new_cont.. │
│   r = c.run("echo hello")          r = await c.run("echo hi")  │
│   c.shutdown()                      await c.shutdown()           │
└──────────────┬───────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│  pocketdock SDK                                                 │
│                                                                  │
│  ┌──────────────────────────────────────┐                        │
│  │  Sync Container ──► AsyncContainer   │  (facade pattern)      │
│  │                     │                │                        │
│  │                     ├── SocketClient │  (one conn per op)     │
│  │                     ├── SocketClient │  (streaming conn)      │
│  │                     └── SocketClient │  (detached conn)       │
│  └──────────────────────────────────────┘                        │
│  ┌──────────────────┐  ┌──────────────────────┐                  │
│  │  ContainerPool    │  │  ProjectManager      │                  │
│  │  Persistence      │  │  Errors / Logging    │                  │
│  └──────────────────┘  └──────────────────────┘                  │
└──────────────┬──────────────────────────────────────────────────┘
               │  each op opens its own connection
               │  Unix socket (Podman or Docker)
               ▼
┌──────────────────────────────────────────────────────────────────┐
│  Podman Engine (or Docker)                                       │
│                                                                  │
│    ┌───────────┐  ┌───────────┐  ┌───────────┐                  │
│    │ ctr A     │  │ ctr B     │  │ ctr C     │                  │
│    │ (running) │  │ (running) │  │ (exited)  │                  │
│    └───────────┘  └───────────┘  └───────────┘                  │
└──────────────────────────────────────────────────────────────────┘
```

### Why Podman Over Docker

Podman is the recommended engine. Docker is fully supported via its compatible socket.

| Concern | Podman | Docker |
|---|---|---|
| Root daemon | None — daemonless | Requires `dockerd` as root |
| Rootless by default | Yes | Possible but not default |
| Attack surface | Lower (no persistent daemon) | Higher (root daemon) |
| Socket | `$XDG_RUNTIME_DIR/podman/podman.sock` | `/var/run/docker.sock` |
| REST API | Docker-compatible | Docker-native |
| License | Apache 2.0 | Apache 2.0 (Moby) |

From pocketdock's perspective, they're interchangeable. Both expose the same REST API over a Unix socket. The SDK auto-detects which is available.

### Socket Auto-Detection

Detection order:

1. Explicit `POCKETDOCK_SOCKET` env var (if set, use it directly)
2. Podman rootless: `$XDG_RUNTIME_DIR/podman/podman.sock`
3. Podman system: `/run/podman/podman.sock`
4. Docker: `/var/run/docker.sock`
5. Error with helpful message listing what was checked and how to fix it

The SDK implements this detection using stdlib only. No libraries involved — just checking for socket files and making an HTTP request (`GET /_ping`) to verify the engine is responsive.

---

## Shipping Images Offline

We ship Dockerfiles in the repo. The first `pocketdock build` pulls base images from a registry (requires internet). After that, built images are cached locally and all operations are offline — container lifecycle, exec, and file transfer are Unix socket calls with no network dependency.

For air-gapped environments:

```bash
# Connected machine
pocketdock build --all
pocketdock export --all -o pocketdock-images.tar.gz

# Air-gapped machine
pocketdock import pocketdock-images.tar.gz
```

Alpine is the base for `minimal` and `embedded` profiles (~25MB). `python:3.12-slim` (Debian) is the base for `dev` and `agent` profiles (~45MB) because many Python packages assume glibc.

---

## Image Profiles

Four profiles ship as Dockerfiles in `images/` in the repo. Each profile has:

- A **profile name** used in the CLI and SDK: `minimal`, `dev`, `agent`, `embedded`
- A **Dockerfile** in the repo at `images/{profile}/Dockerfile`
- A **built image tag** in Podman's local registry: `pocketdock/{profile}` (e.g. `pocketdock/minimal`)

`pocketdock build` builds the Dockerfiles and tags them locally. After that, the profile name is all you use:

```bash
pocketdock create --profile embedded        # uses image tagged pocketdock/embedded
pocketdock shell dev                         # uses image tagged pocketdock/dev
```

```python
create_new_container(profile="agent")         # uses image tagged pocketdock/agent
```

### Profile: `minimal`

**Purpose:** Lightest possible sandbox. Good default for agents.

```dockerfile
FROM alpine:3.21
RUN apk add --no-cache python3 py3-pip bash
RUN adduser -D -s /bin/bash sandbox
USER sandbox
WORKDIR /home/sandbox
CMD ["sleep", "infinity"]
```

- **Size:** ~25MB
- **Contains:** Python 3, pip, bash, busybox utils
- **Network:** Disabled by default
- **Use case:** LLM agent runs generated Python, reads stdout, destroys container

### Profile: `dev`

**Purpose:** Interactive development sandbox with common tools.

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git jq vim-tiny tree htop less \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir ipython requests httpx
RUN useradd -m -s /bin/bash sandbox
USER sandbox
WORKDIR /home/sandbox
CMD ["sleep", "infinity"]
```

- **Size:** ~250MB
- **Contains:** Python 3.12, pip, git, curl, jq, vim, build tools, ipython
- **Network:** Enabled by default
- **Use case:** `pocketdock shell dev` → disposable dev environment

### Profile: `agent`

**Purpose:** Python sandbox with common libraries pre-installed for agent tasks.

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl jq git \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir \
    requests httpx beautifulsoup4 lxml \
    pandas numpy \
    pyyaml toml \
    pillow
RUN useradd -m -s /bin/bash sandbox
USER sandbox
WORKDIR /home/sandbox
CMD ["sleep", "infinity"]
```

- **Size:** ~350MB
- **Contains:** Python + common data/web/parsing libraries
- **Network:** Disabled by default
- **Use case:** Agent tasks that need real libraries (parse HTML, process data) without waiting for pip install

### Profile: `embedded`

**Purpose:** C/C++ toolchain for embedded development, cross-compilation, and IoT platforms (Arduino, ESP32, ARM).

```dockerfile
FROM alpine:3.21

# Core toolchain
RUN apk add --no-cache \
    gcc g++ musl-dev make cmake ninja \
    gdb valgrind strace \
    git curl wget unzip \
    python3 py3-pip bash

# ARM cross-compiler (Cortex-M, STM32, nRF, etc.)
RUN apk add --no-cache \
    arm-none-eabi-gcc arm-none-eabi-newlib arm-none-eabi-gdb

# Arduino CLI
RUN wget -qO- https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh -s 1.1.1 \
    && mv bin/arduino-cli /usr/local/bin/

# PlatformIO (manages ESP32/ESP-IDF, AVR, and other toolchains)
RUN pip install --no-cache-dir --break-system-packages \
    platformio meson

# Pre-install Arduino cores for offline use (optional, adds ~200MB)
# Uncomment the platforms you need, then rebuild:
# RUN arduino-cli core install arduino:avr
# RUN arduino-cli core install esp32:esp32

RUN adduser -D -s /bin/bash sandbox
USER sandbox
WORKDIR /home/sandbox
CMD ["sleep", "infinity"]
```

- **Size:** ~450MB base (grows with platform cores)
- **Contains:** GCC, G++, CMake, Ninja, GDB, Valgrind, ARM cross-compiler, Arduino CLI, PlatformIO
- **Network:** Enabled by default
- **Use case:** Compile firmware, run host-side unit tests, cross-compile for ARM/AVR/ESP32

**Arduino workflow:**

```python
c = create_new_container(profile="embedded", persist=True, name="arduino-dev")

# First time: install the core you need (requires network, cached after)
c.run("arduino-cli core install esp32:esp32", timeout=300)

# Compile a sketch
c.push("./my_sketch/", "/home/sandbox/my_sketch/")
result = c.run("arduino-cli compile --fqbn esp32:esp32:esp32 my_sketch/")
print(result.stdout)  # compilation output

# Pull the binary back to host for flashing
c.pull("/home/sandbox/my_sketch/build/esp32.esp32.esp32/my_sketch.ino.bin", "./firmware.bin")
```

**ESP32 / ESP-IDF workflow (via PlatformIO):**

```python
c = create_new_container(profile="embedded", persist=True, name="esp-project")

# First time: PlatformIO auto-downloads ESP-IDF toolchain on first build (~600MB, cached after)
c.push("./platformio_project/", "/home/sandbox/project/")
result = c.run("cd project && pio run", timeout=600, stream=True)
for chunk in result:
    print(chunk.data, end="")  # watch the build in real-time

# Pull firmware
c.pull("/home/sandbox/project/.pio/build/esp32dev/firmware.bin", "./firmware.bin")
```

**Offline strategy for embedded:** The toolchains (Arduino cores, PlatformIO platforms, ESP-IDF) are large and download on first use. The best approach is:

1. Create a persistent container with `persist=True`
2. Install your target platforms once (needs network)
3. Toolchains are cached in the container's filesystem
4. Snapshot if you want to freeze the environment: `c.snapshot("my-esp32-toolchain:v1")`
5. All subsequent builds are fully offline

For air-gapped setups, snapshot the fully-configured container and export it:

```bash
pocketdock snapshot esp-project my-embedded-env:v1
pocketdock export --image my-embedded-env:v1 -o embedded-env.tar.gz
# Transfer to air-gapped machine, import there
```

Note: Flashing hardware from inside a container requires USB passthrough (`--device /dev/ttyUSB0`), which pocketdock supports via the `devices` parameter:

```python
c = create_new_container(profile="embedded", devices=["/dev/ttyUSB0"])
c.run("arduino-cli upload --fqbn esp32:esp32:esp32 -p /dev/ttyUSB0 my_sketch/")
```

### Custom Profiles

Users can add their own Dockerfiles or extend existing profiles:

```python
c = create_new_container(image="my-custom-image:latest")
```

```dockerfile
FROM pocketdock/embedded
RUN apk add --no-cache avr-gcc avr-libc
```

---

## SDK Interface

The primary object is a `Container`. You create one, interact with it, and shut it down.

The SDK is zero-dependency. It talks raw HTTP over the Unix socket to the container engine's REST API. No `docker-py`. No `podman-py`. Python's `asyncio` + `http.client` over a Unix socket adapter — stdlib only.

The core implementation is async (`AsyncContainer`). A sync facade (`Container`) wraps it for simple use. See the **Connection and Concurrency Model** section for details. All examples below use the sync API unless noted.

### Core API

#### `create_new_container(**params) → Container`

Factory function. Creates and starts a container, returns a handle. Automatically sets `pocketdock.*` labels on the container for discovery (see Container Discovery section). If `persist=True`, creates an instance directory under `.pocketdock/instances/` in the project root (or cwd).

```python
from pocketdock import create_new_container

# All params have sensible defaults
container = create_new_container()

# Override what you need
container = create_new_container(
    profile="agent",              # "minimal" | "dev" | "agent" | "embedded" (default: "minimal")
    image=None,                   # override profile with any image string
    name=None,                    # auto-generated if not set (e.g. "pd-a1b2c3d4")
    project=None,                 # project name for labeling (default: from pocketdock.yaml or cwd name)
    data_dir=None,                # where instance data lives (default: .pocketdock/instances/{name}/)
    mem_limit="256m",             # memory cap
    cpu_percent=50,               # percent of one core
    network=None,                 # default set by profile (minimal/agent=False, dev/embedded=True)
    ports={},                     # port mapping: {host_port: container_port} e.g. {8080: 8080}
    timeout=30,                   # default exec timeout in seconds
    persist=False,                # if True, container survives shutdown
    volumes={},                   # host:container mount mappings
    devices=[],                   # host devices to expose (e.g. ["/dev/ttyUSB0"])
    env={},                       # environment variables
    workdir="/home/sandbox",      # working directory inside container
)
```

#### `container.run(command, **params) → ExecResult`

Execute a command inside the container and get the output. This is the method you'll call most, so it's worth understanding how output works.

**How it works under the hood.** The container engine's exec API has two steps: (1) create an exec instance (`POST /containers/{id}/exec`), (2) start it and attach to the output stream (`POST /exec/{id}/start`). The output comes back as a multiplexed byte stream — 8-byte header per frame (1 byte stream type, 3 padding, 4-byte big-endian payload length) followed by the payload. pocketdock demultiplexes this into separate stdout and stderr strings.

**Three execution modes:**

**Mode 1: Blocking (default).** Runs the command, waits for it to finish, returns all output at once. This is the right choice 90% of the time.

```python
result = container.run("echo hello")
result.stdout      # "hello\n"
result.stderr      # ""
result.exit_code   # 0
result.ok          # True
result.duration_ms # 47

# Python code
result = container.run("print('hello')", lang="python")

# Multiline script (written to temp file inside container, then executed)
result = container.run("""
import pandas as pd
df = pd.DataFrame({"x": [1,2,3]})
print(df.describe())
""", lang="python")

# Override timeout (default: 30s)
result = container.run("make -j$(nproc)", timeout=300)

# Cap output size (default: 10MB) — prevents runaway processes from OOM'ing the host
result = container.run("cat /dev/urandom | base64", max_output="1m", timeout=5)
```

If the command doesn't exit within `timeout` seconds, pocketdock kills the exec process and returns an `ExecResult` with `exit_code=-1`, `ok=False`, and a timeout indicator in stderr. The container itself is not affected — only the exec process is killed.

If output exceeds `max_output`, the stream is truncated and a warning is appended to stderr. This protects against an LLM agent accidentally running `cat` on a huge file.

**Mode 2: Streaming.** Yields output chunks as they arrive. The command still runs to completion (or timeout), but you see output in real-time. Essential for builds, long-running scripts, and agent monitoring. Note: streaming is inherently async — it uses `async for`. In the sync API, use it inside a `for` loop via a sync iterator wrapper.

```python
# Async API (native)
async for chunk in container.run("make all 2>&1", stream=True):
    print(chunk.data, end="")
    # chunk.stream = "stdout" | "stderr"
    # chunk.data = string content

# Sync API (wrapper — works the same way)
for chunk in container.run("make all 2>&1", stream=True):
    print(chunk.data, end="")

# Collect final result after stream completes
result = container.run("make all", stream=True)
for chunk in result:
    pass
result.exit_code   # available after iteration completes
```

Streaming mode uses the same multiplexed stream — it just yields frames as they arrive rather than buffering everything. The `ExecResult` is finalized once the stream ends.

**Mode 3: Detached.** Starts the command and returns immediately. You get a `Process` handle to check on it later. This is for long-running processes — servers, watchers, background tasks — that you want running inside the container while you do other things.

```python
# Start a background process
proc = container.run("python -m http.server 8080", detach=True)

proc.id             # exec instance ID
proc.is_running()   # True
proc.kill()         # sends SIGTERM
proc.kill(signal=9) # sends SIGKILL

# Read whatever output has accumulated so far (non-blocking)
output = proc.read()  
output.stdout        # partial stdout up to this point

# Wait for it to finish (blocking, with optional timeout)
result = proc.wait(timeout=60)  # returns ExecResult

# Common pattern: start server, do work, tear down
proc = container.run("python server.py", detach=True)
container.run("curl localhost:8080/health")  # runs alongside the server
proc.kill()
```

**What about interactive commands?**

If something like `python` (no script), `bash`, `vim`, or `top` is run via `container.run()`, it will appear to hang because these programs wait for stdin, which `run()` doesn't provide. The timeout will eventually kill it, and you'll get an error.

Interactive use is handled by a separate method:

```python
# Attach an interactive TTY — for human use, not agents
container.shell()             # drops into bash (default)
container.shell("python")    # drops into Python REPL
container.shell("vim foo.c") # opens vim
```

`shell()` creates the exec with `Tty: true` and `AttachStdin: true`, then hands off to the terminal. In the CLI, `pocketdock shell` does this. In the SDK, `shell()` takes over the calling process's stdin/stdout/stderr for the duration. It's explicitly not designed for programmatic use — there's no way to script it.

**For agents, the rule is simple:** use `run()` for everything. If you need to interact with a process, start it detached and talk to it via files, HTTP, or stdin piping (future feature). Don't try to script interactive tools.

**Summary of modes:**

| Mode | Use case | Returns | Blocks? | Gets stdin? |
|---|---|---|---|---|
| Blocking (default) | Scripts, commands, builds | `ExecResult` | Yes, until done or timeout | No |
| `stream=True` | Long builds, monitoring | Async iterator → `ExecResult` | Yields chunks, then done | No |
| `detach=True` | Servers, background tasks | `Process` handle | No, returns immediately | No |
| `shell()` | Human interaction, debugging | Nothing (takes over terminal) | Yes, until user exits | Yes (TTY) |

#### `container.shell(command="bash")`

Attach an interactive TTY to the container. Takes over the calling process's terminal. For human use — debugging, exploration, interactive tools.

```python
container.shell()              # bash
container.shell("python")     # Python REPL
container.shell("vim main.c") # vim
```

This is fundamentally different from `run()` — it creates the exec with `Tty: true` and `AttachStdin: true`, connects stdin/stdout/stderr directly, and blocks until the user exits. The CLI command `pocketdock shell` wraps this.

#### `container.info() → ContainerInfo`

Point-in-time snapshot of the container's state. Call it as often as you like — each call is a fresh poll from the engine.

```python
info = container.info()

# Identity
info.id              # "a1b2c3d4e5f6"
info.name            # "pd-a1b2c3d4"
info.status          # "running" | "stopped" | "paused"
info.image           # "pocketdock/agent"
info.profile         # "agent"
info.project         # "my-agent"
info.created_at      # datetime
info.uptime          # timedelta

# Resource usage (live, polled)
info.memory_usage    # "42.1 MB"
info.memory_limit    # "256 MB"
info.memory_percent  # 16.4
info.cpu_percent     # 3.2
info.pids            # 2

# Network
info.network         # True/False
info.ip_address      # "172.17.0.2" or None

# Filesystem
info.disk_usage      # "12.3 MB" (writable layer size)

# Running processes
info.processes       # [{"pid": 1, "cmd": "sleep infinity"}, ...]
```

Under the hood this hits three API endpoints: `/containers/{id}/json` (inspect), `/containers/{id}/stats?stream=false` (one-shot stats), and `/containers/{id}/top` (process list).

#### `container.reboot()`

Restart the container. Preserves the filesystem (writable layer) but kills all running processes and resets memory state.

```python
container.reboot()

# Rebuild from clean image (wipes filesystem too)
container.reboot(fresh=True)
```

#### `container.shutdown()`

Stop and remove the container. If `persist=True` was set at creation, the container is stopped but not removed — it can be resumed later.

```python
container.shutdown()             # stop + remove (default)
container.shutdown(force=True)   # kill -9 + remove (if hung)
```

### File Operations

```python
# Write a file into the container
container.write_file("/home/sandbox/config.json", '{"debug": true}')

# Read a file from the container
content = container.read_file("/home/sandbox/output.txt")

# List directory contents
files = container.list_files("/home/sandbox/")

# Copy file: host → container
container.push("./local_file.py", "/home/sandbox/file.py")

# Copy file: container → host
container.pull("/home/sandbox/output.csv", "./output.csv")

# Sync a local directory into the container
container.push("./src/", "/home/sandbox/src/")
```

These are implemented via the container engine's archive API (`PUT /containers/{id}/archive` for push, `GET /containers/{id}/archive` for pull) which uses tar streams.

### Context Manager / Disposable Pattern

```python
# Auto-shutdown on exit (even on crash / KeyboardInterrupt)
with create_new_container(profile="agent") as c:
    c.run("print('hello')")
# container is destroyed here
```

### Pool

For high-throughput agent workloads where you're creating/destroying containers rapidly.

```python
from pocketdock import ContainerPool

pool = ContainerPool(size=5, profile="minimal")
pool.start()                    # pre-creates 5 containers

container = pool.acquire()      # ~instant (already running)
result = container.run(code)
pool.release(container)         # returns to pool, not destroyed

pool.shutdown()                 # destroys all
```

### ExecResult

Every `run()` call returns:

```
{
  exit_code: number      # 0 = success, -1 = timeout
  stdout: string         # captured stdout
  stderr: string         # captured stderr
  ok: boolean            # exit_code === 0
  duration_ms: number    # wall-clock execution time
  timed_out: boolean     # true if killed by timeout
  truncated: boolean     # true if output exceeded max_output
}
```

---

## Connection and Concurrency Model

This is the most architecturally important section of the spec. Get this wrong and everything on top is fragile.

### The communication path

```
┌────────────┐      ┌────────────┐      ┌─────────────────────────┐
│ Container A │      │ Container B │      │ Container C (dead)      │
│ (object)    │      │ (object)    │      │ (object, stale handle)  │
└──────┬─────┘      └──────┬─────┘      └──────┬──────────────────┘
       │                   │                    │
       │ conn A            │ conn B             │ conn C
       │                   │                    │
       ▼                   ▼                    ▼
┌──────────────────────────────────────────────────────────────────┐
│                     Unix Socket                                  │
│          /run/user/1000/podman/podman.sock                       │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                     Podman Engine                                 │
│                                                                  │
│    ┌───────────┐    ┌───────────┐    ┌───────────┐              │
│    │ ctr A     │    │ ctr B     │    │ ctr C     │              │
│    │ (running) │    │ (running) │    │ (exited)  │              │
│    └───────────┘    └───────────┘    └───────────┘              │
└──────────────────────────────────────────────────────────────────┘
```

Critical point: **the socket connects to Podman, not to the container.** When container C crashes, the socket is still healthy. Podman knows container C is dead and will return appropriate HTTP errors (404 Not Found, 409 Conflict) when you try to exec into it. Containers A and B are completely unaffected.

### Each container owns its own connection

Every `Container` object creates its own independent connection to the Podman socket. This means:

- Container A can be in the middle of a streaming `run()` while container B starts a blocking `run()`. Neither blocks the other.
- If container A's connection enters a bad state (stuck read, broken pipe from a Podman restart), container B's connection is unaffected.
- Shutting down container A closes connection A. Container B doesn't notice.

Unix socket connections are essentially free — no TCP handshake, no TLS negotiation, nanosecond-scale overhead. There is no reason to share connections and every reason not to.

### Connection lifecycle within a container

A single Container may need multiple simultaneous connections:

```
Container A
├── conn 1: blocking run("echo hello")      → opens, sends, reads, closes
├── conn 2: streaming run("make", stream=True)  → opens, streams until done, closes
├── conn 3: detached run("server.py", detach=True)  → opens, stays open while server runs
└── conn 4: info()  → opens, reads, closes (even while conn 2/3 are active)
```

The strategy: **open a new connection per operation.** Blocking and info calls open a connection, do their work, close it. Streaming holds a connection open for the duration of the stream. Detached holds a connection open for the lifetime of the background process.

This is simpler than connection pooling and has no practical cost on Unix sockets. The Podman engine handles hundreds of concurrent connections without issue.

### Async core, sync facade

The I/O is inherently async — you're sending HTTP requests and waiting for responses over a socket. The natural implementation is async. But most users want sync.

**The core is async.** `AsyncContainer` with `await c.run()`, using `asyncio` for non-blocking I/O.

**The sync facade** wraps it for simple use. It manages a background event loop thread so the user never sees `async/await` unless they want to.

```python
# --- Sync (default import, simple scripts, agent loops) ---
from pocketdock import create_new_container

c1 = create_new_container(profile="minimal")
c2 = create_new_container(profile="minimal")

r1 = c1.run("echo 1")   # blocks until done
r2 = c2.run("echo 2")   # blocks until done (sequential)

c1.shutdown()
c2.shutdown()
```

```python
# --- Async (concurrent operations, high-throughput agents) ---
from pocketdock.async_ import create_new_container
import asyncio

async def main():
    c1 = await create_new_container(profile="minimal")
    c2 = await create_new_container(profile="minimal")

    # Run in both containers simultaneously
    r1, r2 = await asyncio.gather(
        c1.run("sleep 2 && echo done-1"),
        c2.run("sleep 2 && echo done-2"),
    )
    # Takes ~2 seconds total, not ~4

    await c1.shutdown()
    await c2.shutdown()

asyncio.run(main())
```

```python
# --- Mixed: sync containers, but concurrent via threads ---
from pocketdock import create_new_container
from concurrent.futures import ThreadPoolExecutor

containers = [create_new_container() for _ in range(5)]

with ThreadPoolExecutor(max_workers=5) as pool:
    futures = [pool.submit(c.run, agent_code) for c in containers]
    results = [f.result() for f in futures]

for c in containers:
    c.shutdown()
```

**Why not just async everywhere?** Because `result = c.run("echo hello")` is a better developer experience than `result = await c.run("echo hello")` for the 80% case where you have one container doing things sequentially. Forcing async on everyone to handle the concurrent case is the wrong trade-off for a tool like this.

**Why not just sync everywhere?** Because when you have 5 containers and you want to run code in all 5 simultaneously, blocking sync forces you into threads. Threads work, but asyncio is cleaner for I/O-bound concurrency, and this is pure I/O.

**Implementation approach:** The async version is the real implementation. The sync version is a thin wrapper:

```python
# Simplified — actual implementation handles edge cases
class Container:
    """Sync facade over AsyncContainer."""
    
    def __init__(self, async_container, loop, thread):
        self._ac = async_container
        self._loop = loop      # background event loop
        self._thread = thread  # thread running the loop
    
    def run(self, command, **kwargs):
        future = asyncio.run_coroutine_threadsafe(
            self._ac.run(command, **kwargs),
            self._loop,
        )
        return future.result(timeout=kwargs.get("timeout", 30))
```

This means the sync version is thread-safe by construction — each call dispatches to the background event loop, which serializes operations naturally.

### What happens when a container dies

Containers can die unexpectedly: OOM killed, process crash, external `podman rm`, host reboot. The `Container` object doesn't know this until it tries to talk to the engine. Here's the error model:

```python
c = create_new_container(profile="minimal")

# Meanwhile, container is killed externally: podman kill <id>

try:
    result = c.run("echo hello")
except ContainerNotRunning as e:
    print(e)
    # "Container pd-a1b2c3d4 is not running (status: exited, exit code: 137).
    #  The container was likely killed externally (OOM, signal, or manual removal).
    #  Use c.info() to inspect, c.reboot() to restart, or c.shutdown() to clean up."
    
    c.info().status   # "exited"
    c.reboot()        # restarts it
    c.run("echo back")  # works again
```

```python
# Container was fully removed (podman rm)
try:
    result = c.run("echo hello")
except ContainerGone as e:
    print(e)
    # "Container pd-a1b2c3d4 no longer exists. It was removed outside pocketdock.
    #  Instance metadata preserved at .pocketdock/instances/pd-a1b2c3d4/
    #  Create a new container with create_new_container()."
```

Key behaviors:

- **`ContainerNotRunning`**: Container exists but isn't running. `reboot()` can fix it. `info()` still works.
- **`ContainerGone`**: Container was removed entirely. Object is useless. Local instance metadata still exists for forensics.
- **Other containers are never affected.** Each Container has its own connection. One dying doesn't poison anything.
- **The Container object never lies.** It doesn't cache status. `info()` always polls live. If the container is dead, you find out immediately.
- **Errors are actionable.** The exception message tells you what happened and what you can do about it.

### Streaming and the connection budget

Streaming is the case that makes shared connections break. When `run(stream=True)` is active, that connection is held open for the duration — it's reading chunked HTTP response frames as they arrive. If you shared one connection, nothing else could use it during a stream.

With connection-per-operation, this is a non-issue:

```python
# These can all happen simultaneously in async mode
stream = c.run("make -j8 2>&1", stream=True)   # holds conn 1 open
proc = c.run("python server.py", detach=True)    # holds conn 2 open
info = c.info()                                   # opens conn 3, reads, closes
result = c.run("echo quick-check")                # opens conn 4, reads, closes
```

Each operation opens its own connection. Podman multiplexes them. The Container object just tracks which operations are active so it can clean them up on `shutdown()`.

### Cleanup guarantees

When `shutdown()` is called (or the context manager exits, or `atexit` fires):

1. Kill all active detached processes
2. Cancel all active streams (close their connections)
3. Stop the container (`POST /containers/{id}/stop`)
4. Remove the container if `persist=False` (`DELETE /containers/{id}`)
5. Close all remaining connections
6. Update local instance metadata

If the Python process crashes hard (SIGKILL), steps 1-6 don't run. The container is still alive in Podman. This is where container labels help — `pocketdock doctor` can find orphaned containers (labeled `pocketdock.managed=true` but with no corresponding running pocketdock process) and clean them up.

### Output buffer and callbacks

Every active operation (streaming `run()`, detached `run()`) produces output in the background. That output needs to go somewhere, whether or not you're paying attention. The model has three layers: buffer, pull, push.

**The buffer.** Output is accumulated automatically into a bounded ring buffer (default: 1MB per operation). If you never read it, it's there. If the buffer fills, oldest data is evicted. The buffer exists to decouple "output is being produced" from "someone is consuming it."

```python
proc = c.run("make -j8 2>&1", detach=True)

# ... do other work for 30 seconds ...

# Read whatever has accumulated (drains the buffer)
output = proc.read()
print(output.stdout)   # all buffered stdout up to this point

# Read again — only gets what arrived since last read()
more = proc.read()

# Peek without draining
peeked = proc.peek()

# Check how much is buffered
proc.buffer_size        # bytes currently in buffer
proc.buffer_overflow    # True if anything was evicted
```

**Pull: read when you want.** `proc.read()` drains accumulated output and returns it. Non-blocking — returns immediately with whatever's available (empty string if nothing). This is for polling patterns where you check periodically:

```python
proc = c.run("training_job.py", detach=True, lang="python")

while proc.is_running():
    chunk = proc.read()
    if chunk.stdout:
        parse_metrics(chunk.stdout)
    time.sleep(5)

final = proc.wait()
```

**Push: callbacks for real-time reaction.** Register functions that fire when output arrives. Callbacks run on the background event loop thread — they don't block your main code, but they also shouldn't do heavy work (offload to a queue if needed).

```python
c = create_new_container(profile="agent")

# Register before or after run() — both work
c.on_stdout(lambda container, data: print(f"[{container.name}] {data}", end=""))
c.on_stderr(lambda container, data: log.warning(f"[{container.name}] {data}"))
c.on_exit(lambda container, exit_code: print(f"[{container.name}] exited: {exit_code}"))

proc = c.run("python agent_task.py", detach=True)
# callbacks fire as output arrives — you don't need to poll
```

Callbacks receive the container as the first argument so a single callback function can handle multiple containers:

```python
def on_output(container, data):
    print(f"[{container.name}] {data}", end="")

c1 = create_new_container(name="agent-1")
c2 = create_new_container(name="agent-2")

c1.on_stdout(on_output)
c2.on_stdout(on_output)

# Output from both containers flows into the same handler, labeled by name
c1.run("python task_a.py", detach=True)
c2.run("python task_b.py", detach=True)
```

**Callbacks vs streaming vs buffer — when to use which:**

| Pattern | Use when | You write |
|---|---|---|
| Blocking `run()` | One-shot commands, scripts | `result = c.run("echo hi")` |
| Streaming `run(stream=True)` | You want to process output line-by-line as primary activity | `for chunk in c.run(...)` (sync) / `async for` (async) |
| Detached + buffer | Fire and forget, check later | `proc = c.run(..., detach=True)` then `proc.read()` |
| Detached + callbacks | React to output in real-time while doing other things | `c.on_stdout(fn)` then `c.run(..., detach=True)` |

These compose. You can have callbacks registered *and* read the buffer *and* have multiple detached processes — all on the same container. **Callbacks and buffer are independent.** Callbacks get a copy. The buffer gets a copy. Reading the buffer doesn't affect callbacks. Registering callbacks doesn't drain the buffer. This avoids a class of subtle bugs where registering a callback accidentally drains output that something else was relying on.

### Sessions: persistent shell connections

The `run()` model creates a new exec instance per call. Each call is independent — no shared state, no shell history, no environment variable changes carrying over. This is by design for agent use: every call is deterministic and isolated.

But sometimes you want a persistent shell. You're debugging, or your workflow involves a sequence of commands where each depends on the prior state (`cd`, `export`, `source`, `activate`), or you want to interact with a REPL.

A `Session` is a persistent connection to a shell process inside the container. Commands sent through a session share state because they're all executing in the same shell process.

```python
# Open a session — starts a bash process and attaches to it
session = c.session()

# Send commands — they execute in the same bash process
session.send("cd /home/sandbox/project")
session.send("export FLASK_ENV=development")
session.send("source venv/bin/activate")
result = session.send("python app.py &")
# All of these share the same shell — cd, export, source all persist

# Read output (works like the buffer model)
output = session.read()

# Or use callbacks
session.on_output(lambda data: print(data, end=""))

# Send and wait for a specific result
result = session.send_and_wait("make test")
print(result.exit_code)  # derived from `echo $?` after command

# Interactive: hand the session to the terminal (like shell())
session.interactive()  # takes over stdin/stdout until user exits

# Close the session (kills the shell process, not the container)
session.close()
```

**How it works under the hood:** A session creates a single exec instance with `AttachStdin: true` and `Tty: true` (for interactive use) or `Tty: false` (for programmatic use). The connection stays open. Commands are written to stdin. Output comes back through the multiplexed stream. The tricky part is knowing when a command has finished — the session appends a sentinel marker after each command (`echo __PD_SENTINEL_$?__`) and parses it out of the output to determine when the command completed and what the exit code was.

**Session vs run() — when to use which:**

| | `run()` | `session.send()` |
|---|---|---|
| State between calls | None (each exec is fresh) | Shared (same shell process) |
| Environment variables | Set via `env={}` at container creation | `export` persists across sends |
| Working directory | Always `workdir` | `cd` persists |
| Determinism | High — each call is isolated | Lower — depends on prior state |
| Agent use | Preferred — predictable | Use when state matters |
| Human debugging | Works but clunky | Natural — feels like a terminal |

**Sessions and callbacks compose with everything else.** You can have a session open *and* run detached processes *and* have callbacks on both — they use separate connections.

```python
c = create_new_container(profile="dev", persist=True, name="my-dev")

# Agent uses run() for isolated tasks
result = c.run("python -c 'print(1+1)'")

# Developer opens a session for interactive debugging
session = c.session()
session.on_output(lambda data: debug_log.write(data))
session.send("cd /project && git status")

# Background process runs alongside both
proc = c.run("python -m http.server 8080", detach=True)
c.on_stdout(lambda c, data: print(f"[server] {data}"))

# All three — run(), session, detached — coexist on the same container
```

---

## CLI

The CLI is a first-class part of pocketdock, not an afterthought. It's written in Python using `click` for command structure and `rich` for output formatting. It's installed alongside the SDK (`pip install pocketdock` or `uv add pocketdock` gives you both the library and the `pocketdock` command).

### Design Principles

- **Beautiful defaults.** Rich-formatted tables, colored status indicators, clear error messages with suggestions.
- **No silent destruction.** Any command that deletes data asks for confirmation. `--yes` / `-y` flag to skip in scripts.
- **Built-in logging.** Every command logs structured output to `.pocketdock/logs/` in the project root. Configurable log level via `--verbose` / `--quiet`. `--log-file` to redirect.
- **Helpful errors.** If Podman isn't running, don't just say "connection refused" — say "Podman doesn't appear to be running. Try: systemctl --user start podman.socket"

### Commands

```
pocketdock build [PROFILE...]        Build image profiles (default: all)
pocketdock build minimal embedded    Build specific profiles

pocketdock init [OPTIONS]            Initialize a project (creates .pocketdock/pocketdock.yaml)
  --profile TEXT                      Set default profile
  --name TEXT                         Project name (default: directory name)

pocketdock create [OPTIONS]          Create and start a new container
  --profile / -p TEXT                 Image profile (minimal/dev/agent/embedded)
  --image TEXT                        Custom image (overrides --profile)
  --project TEXT                      Project label (default: from pocketdock.yaml or cwd name)
  --name TEXT                         Container name (auto-generated if omitted)
  --data-dir PATH                     Instance data location (default: .pocketdock/instances/{name}/)
  --mem TEXT                          Memory limit (e.g. "256m", "1g")
  --cpu INT                           CPU percent (1-100)
  --network / --no-network            Enable/disable networking
  --port TEXT                         Port mapping (host:container), repeatable
  --timeout INT                       Default exec timeout in seconds (default: 30)
  --persist                           Keep container on shutdown
  --volume TEXT                       Mount volume (host:container), repeatable
  --device TEXT                       Expose host device (e.g. /dev/ttyUSB0), repeatable
  --env TEXT                          Environment variable (KEY=VALUE), repeatable
  --workdir TEXT                      Working directory inside container

pocketdock list [OPTIONS]            List containers
  --project TEXT                      Filter by project label (default: current project if in one)
  --all-projects                      Show containers from all projects
  --running                           Show only running containers
  --all / -a                          Include stopped containers
  --json                              Output as JSON (for scripting)

pocketdock info CONTAINER            Show detailed container info
  --json                              Output as JSON

pocketdock run CONTAINER COMMAND     Execute a command
  --lang TEXT                         Language (bash/python/node)
  --timeout INT                       Timeout in seconds
  --stream / -s                       Stream output in real-time
  --detach / -d                       Run in background, return immediately
  --max-output TEXT                   Cap output size (e.g. "1m", "10m")

pocketdock shell CONTAINER           Attach interactive shell
pocketdock shell --profile dev       Create ephemeral + attach (shortcut)

pocketdock push CONTAINER SRC DST    Copy files host → container
pocketdock pull CONTAINER SRC DST    Copy files container → host

pocketdock reboot CONTAINER          Restart container
  --fresh                             Rebuild from clean image

pocketdock stop CONTAINER            Stop a persistent container
  --all                               Stop all running containers
pocketdock resume CONTAINER          Resume a stopped persistent container
pocketdock shutdown CONTAINER        Stop + remove (asks confirmation)
  -y / --yes                          Skip confirmation

pocketdock snapshot CONTAINER NAME   Save container state as new image
pocketdock status [OPTIONS]          Show project summary (disk, counts, instance dirs)

pocketdock systemd CONTAINER         Generate a systemd user unit file (stdout)

pocketdock prune [OPTIONS]           Remove stopped containers and stale instance dirs
  --project TEXT                      Prune only containers in this project
  --images                            Also remove unused pocketdock images
  -y / --yes                          Skip confirmation

pocketdock export [OPTIONS]          Export images as tarball
  --all                               All profiles
  --profile TEXT                      Specific profile(s)
  -o FILE                             Output file

pocketdock import FILE               Import images from tarball

pocketdock logs [OPTIONS] [CONTAINER]  View logs
  (no container)                       Show pocketdock operational log
  CONTAINER                            Show stream logs for a container
  --history                            Show structured command history (from history.jsonl)
  --last INT                           Show last N operations (default: 10)
  --tail INT                           Last N lines of a specific log
  --follow / -f                        Follow log output
  --type TEXT                          Filter by type: run, session, detach

pocketdock doctor                     Reconcile labels and local instance data, find problems
                                       - Labeled containers whose data-path doesn't exist (orphaned data)
                                       - Instance dirs with no matching container (stale)
                                       - Label/metadata mismatches (project changed, etc.)
                                       - Port conflicts between running containers
                                       - Disk usage summary for .pocketdock/ in current project
  --fix                               Auto-fix what it can (default: report only)
```

### Example Session

```
$ cd ~/my-widget
$ pocketdock init --profile embedded
✓ Created .pocketdock/pocketdock.yaml (project: my-widget)

$ pocketdock build
Building pocketdock/minimal ... done (25 MB)
Building pocketdock/dev ... done (248 MB)
Building pocketdock/agent ... done (347 MB)
Building pocketdock/embedded ... done (412 MB)

$ pocketdock create --name stm32-dev --persist
✓ Created container stm32-dev (pocketdock/embedded)
  Project: my-widget
  Data:    .pocketdock/instances/stm32-dev/
  Memory:  256 MB
  Network: enabled

$ pocketdock run stm32-dev "arm-none-eabi-gcc --version"
arm-none-eabi-gcc (Alpine 13.2.0) 13.2.0

$ pocketdock list
  NAME        STATUS   PROFILE    AGE      MEMORY
  stm32-dev   running  embedded   2m ago   18.4 MB / 256 MB

$ pocketdock shutdown stm32-dev
Container stm32-dev is persistent. Stop without removing? [Y/n]
✓ Stopped stm32-dev (filesystem preserved, 34 MB on disk)

$ pocketdock resume stm32-dev
✓ Resumed stm32-dev
```

---

## Persistence

Containers are ephemeral by default — `shutdown()` removes them completely. pocketdock supports four levels of persistence:

### Level 0: Ephemeral (default)

Container is destroyed on `shutdown()`. Nothing survives.

```python
container = create_new_container()      # persist=False (default)
container.run("pip install flask")
container.shutdown()                     # gone — flask is not installed next time
```

### Level 1: Stopped Container (`persist=True`)

Container is stopped but not removed. Filesystem preserved. Memory state (running processes, variables) is lost.

```python
# Session 1
container = create_new_container(profile="dev", persist=True, name="my-workspace")
container.run("pip install flask")
container.shutdown()                     # stopped, NOT removed

# Session 2
from pocketdock import resume_container
container = resume_container("my-workspace")
container.run("python -c 'import flask; print(flask.__version__)'")  # still there
```

### Level 2: Volume Mounts (explicit host directories)

Mount a host directory into the container. Files there persist regardless of container lifecycle.

```python
container = create_new_container(
    profile="agent",
    volumes={"./workspace": "/home/sandbox/workspace"}
)
container.run("echo 'persisted' > /home/sandbox/workspace/output.txt")
container.shutdown()      # container gone, ./workspace/output.txt remains
```

### Level 3: Snapshot / Commit (save as new image)

Commit the container's current state as a new image.

```python
container = create_new_container(profile="minimal")
container.run("pip install torch transformers", timeout=300)
container.snapshot("my-ml-sandbox:v1")
container.shutdown()

# Later — new containers from the snapshot
c = create_new_container(image="my-ml-sandbox:v1")
```

**Trade-offs:**

| Level | Survives shutdown? | Survives host reboot? | Portable? | Disk cost |
|---|---|---|---|---|
| 0 — Ephemeral | ❌ | ❌ | N/A | Zero |
| 1 — Stopped | ✅ (filesystem) | ✅ | ❌ (tied to engine) | Low–Medium |
| 2 — Volumes | ✅ (mounted dirs) | ✅ | ✅ (just files) | You control it |
| 3 — Snapshot | ✅ (full image) | ✅ | ✅ (exportable) | Medium–High |

---

## Project Organization and Local Data

### Terminology

Three concepts, clearly separated:

| Term | What it is | Where it lives | Scope |
|---|---|---|---|
| **Container** | The actual Podman/Docker container (running or stopped) | Podman's container registry | Machine-wide. Visible from any terminal, any directory, any user with access to the Podman socket. A container with port 8080 mapped is reachable from anywhere on the machine (and the LAN if the firewall allows). |
| **Instance** | pocketdock's metadata record for a container it created | `.pocketdock/instances/{name}/` in the project directory | Local to the project. Contains provenance, command history, stream logs. Created only for persistent containers. |
| **Project** | A directory containing `.pocketdock/pocketdock.yaml` | Any directory the user works in | Defines default profile, project name (used in container labels), and data layout. Similar to `.git/` — pocketdock walks up from cwd to find it. |

### No global registry

There is no `~/.pocketdock/projects/` directory. No centralized instance store. Instance data lives in the project tree, next to the code it belongs to.

The only global file is `~/.pocketdock/pocketdock.yaml` — optional install-level preferences (socket path, default profile, log level). It contains no instance data.

### Container discovery: how pocketdock finds its containers

Podman keeps a flat, machine-wide list of all containers. pocketdock needs to know which of those are "ours." Two mechanisms work together:

**1. Podman labels (source of truth for identity).** When pocketdock creates a container, it sets OCI labels on it:

```
pocketdock.managed = "true"
pocketdock.project = "my-widget"
pocketdock.instance = "pd-a1b2c3d4"
pocketdock.profile = "embedded"
pocketdock.data-path = "/home/alice/my-widget/.pocketdock/instances/pd-a1b2c3d4"
pocketdock.created-at = "2026-02-05T09:15:00Z"
```

These labels are stored by Podman on the container itself. They survive stop/start cycles. They're queryable via `podman ps --filter label=pocketdock.managed=true`. The `pocketdock.data-path` label records where instance data lives on disk so `pocketdock doctor` can find it from anywhere.

**2. Local instance data (source of truth for history).** `.pocketdock/instances/{name}/` in the project directory contains `instance.toml`, stream logs, command history, and the `data/` volume mount. Labels tell you *what* a container is; local data tells you *what happened inside it*.

**Discovery behavior:**

- `pocketdock list` (from a project directory): queries Podman for containers with `pocketdock.managed=true`, scopes to current project by matching `pocketdock.project` label. Shows all this project's containers regardless of state.
- `pocketdock list --all-projects`: queries Podman for all pocketdock containers across every project on the machine.
- `pocketdock resume stm32-dev`: tells Podman to start a container by name. Works from anywhere — Podman's name registry is machine-wide.
- `pocketdock doctor` (from a project directory): reconciles labels against local `.pocketdock/instances/` directory. Finds labeled containers whose data-path doesn't exist, instance dirs with no matching container, and label/metadata mismatches.

**What pocketdock does NOT do:**

- Does not provide network isolation between projects. If two containers both map port 8080, the second one fails with a port conflict (Podman error, surfaced clearly by pocketdock).
- Does not restrict cross-project access. Any script on the machine can talk to any pocketdock container.
- Does not track instance data globally. `pocketdock doctor` only reconciles the current project. Stale `.pocketdock/` dirs in abandoned projects are just files taking up space — `podman system prune` handles the container side.

### How pocketdock finds the project root

pocketdock walks up from cwd looking for `.pocketdock/pocketdock.yaml`, similar to how git looks for `.git/`. If found, that directory is the project root. If not found, cwd is used as the project root.

When `pocketdock init` is run, it creates `.pocketdock/pocketdock.yaml` in the current directory, establishing it as a project root.

When a persistent container is created without a project root, `.pocketdock/instances/{name}/` is created relative to cwd. This works but the data ends up wherever you happened to be — same as `git init` in a random directory.

### Directory structure

**Project-level (in the project tree):**

```
~/my-widget/
├── .pocketdock/
│   ├── pocketdock.yaml               # project config (human-authored, maybe committed)
│   ├── logs/
│   │   └── pocketdock.log            # CLI/SDK operational log (rotated)
│   │
│   └── instances/                     # one subdir per persistent container (gitignored)
│       ├── stm32-dev/
│       │   ├── instance.toml          # machine-generated metadata (do not edit)
│       │   ├── logs/                  # automatic stream logs
│       │   │   ├── run-2026-02-05T09-15-00Z.log
│       │   │   ├── run-2026-02-05T09-15-42Z.log
│       │   │   ├── session-2026-02-05T09-20-00Z.log
│       │   │   └── detach-2026-02-05T09-25-00Z.log
│       │   ├── history.jsonl          # structured command history
│       │   └── data/                  # default volume mount target
│       └── pd-e5f6g7h8/
│           ├── instance.toml
│           ├── logs/
│           ├── history.jsonl
│           └── data/
│
├── .gitignore                         # should contain: .pocketdock/instances/
├── src/
└── ...
```

**Install-level (optional global preferences):**

```
~/.pocketdock/
└── pocketdock.yaml                   # install-level defaults (socket path, default profile, log level)
```

No instance data. No project directories. Just preferences.

**Gitignore pattern:**

`.pocketdock/instances/` should be gitignored — instance data is personal (your container IDs, your logs, your command history). `.pocketdock/pocketdock.yaml` is optionally committed — it's project policy (default profile, data layout) that the team might share. Projects that treat container build artifacts as deliverables manage their `.gitignore` accordingly.

### What's in `pocketdock.yaml`

**Project-level** (`.pocketdock/pocketdock.yaml`):

```yaml
# Project configuration for pocketdock
project_name: my-widget              # used in container labels (default: directory name)
default_profile: embedded            # default --profile for pocketdock create
default_persist: false               # default --persist for pocketdock create

logging:
  auto_log: true                     # log all streams to disk (default: true)
  max_log_size: "10MB"               # per-log-file cap
  max_logs_per_instance: 100         # keep most recent N logs per instance
  retention_days: 30                 # auto-prune logs older than this

containers:
  idle_timeout: ""                   # auto-stop after no exec activity (e.g. "4h", disabled by default)
```

**Install-level** (`~/.pocketdock/pocketdock.yaml`):

```yaml
# Install-level defaults — apply when no project config is found
socket: /run/user/1000/podman/podman.sock   # override socket auto-detection
default_profile: minimal
log_level: info                              # debug | info | warning | error
```

Project-level config overrides install-level config. Both are optional — pocketdock works with zero configuration.

### Automatic Stream Logging

Every operation that produces output is automatically logged to disk, organized per instance. This happens in the background — zero configuration, zero overhead for the user. It's the default behavior because the most common regret is not having logs.

**Log file naming:** `{type}-{ISO8601-timestamp}.log`

Types: `run`, `session`, `detach`. Timestamps use second precision, sanitized for filesystems (`T` separator, hyphens instead of colons).

**What's in a log file:**

```
=== pocketdock run log ===
container: pd-a1b2c3d4
command: python -c "import pandas; print(pandas.__version__)"
started: 2026-02-05T09:15:00.123Z
timeout: 30s
---
[stdout 09:15:00.456] 2.1.4
[stderr 09:15:00.457]
---
exit_code: 0
duration_ms: 334
truncated: false
```

**Session logs capture the full dialogue:**

```
=== pocketdock session log ===
container: pd-a1b2c3d4
started: 2026-02-05T09:20:00.000Z
---
[send 09:20:01.100] cd /home/sandbox/project
[recv 09:20:01.150]
[send 09:20:03.200] export FLASK_ENV=development
[recv 09:20:03.210]
[send 09:20:05.300] python app.py
[recv 09:20:05.800] * Running on http://127.0.0.1:5000
[recv 09:20:06.100] * Debug mode: on
---
closed: 2026-02-05T09:25:00.000Z
```

**Detached process logs are the full stream, timestamped:**

```
=== pocketdock detach log ===
container: pd-a1b2c3d4
command: python training_job.py
started: 2026-02-05T09:25:00.000Z
---
[stdout 09:25:01.200] Epoch 1/10 - loss: 0.6823
[stdout 09:25:04.500] Epoch 2/10 - loss: 0.4512
[stderr 09:25:04.501] Warning: learning rate may be too high
[stdout 09:25:07.800] Epoch 3/10 - loss: 0.3201
...
---
exit_code: 0
duration_ms: 28500
```

### Structured Command History

Separate from stream logs, `history.jsonl` records a structured one-line-per-operation summary. This is what `pocketdock logs --history pd-a1b2c3d4` reads.

```jsonl
{"ts":"2026-02-05T09:15:00Z","type":"run","cmd":"python -c \"import pandas; print(pandas.__version__)\"","exit":0,"ms":334,"log":"run-2026-02-05T09-15-00Z.log"}
{"ts":"2026-02-05T09:15:42Z","type":"run","cmd":"pip install flask","exit":0,"ms":12400,"log":"run-2026-02-05T09-15-42Z.log"}
{"ts":"2026-02-05T09:20:00Z","type":"session","sends":14,"duration_s":300,"log":"session-2026-02-05T09-20-00Z.log"}
{"ts":"2026-02-05T09:25:00Z","type":"detach","cmd":"python training_job.py","exit":0,"ms":28500,"log":"detach-2026-02-05T09-25-00Z.log"}
```

JSONL (one JSON object per line) because: parseable by any tool, appendable without reading the whole file, greppable, and `jq` works on it natively.

### Logging Configuration

Logging is configured in `.pocketdock/pocketdock.yaml` (project-level) or `~/.pocketdock/pocketdock.yaml` (install-level). See the `logging:` section in "What's in pocketdock.yaml" above.

```yaml
# .pocketdock/pocketdock.yaml (excerpt)
logging:
  auto_log: true
  log_stdout: true
  log_stderr: true
  max_log_size: "10MB"
  max_logs_per_instance: 100
  retention_days: 30

containers:
  idle_timeout: ""
```

Users who want to disable logging entirely: `auto_log = false`. Users who want unlimited logging: set `max_logs_per_instance = 0` and `retention_days = 0`.

**Relationship between buffer, callbacks, and logs:**

The buffer is for real-time in-memory consumption. Callbacks are for real-time push notifications. Logs are for persistent post-hoc review. All three receive independent copies of the stream. They don't interfere with each other. Disabling one doesn't affect the others.

### What's in `instance.toml`

Machine-generated metadata for one container. Cross-references the Podman container by ID and name. The container itself also carries `pocketdock.*` labels with the same identity info — `instance.toml` adds what labels can't store (provenance, volume paths, history).

```toml
# This file is maintained by pocketdock. Do not edit manually.
# Changes may be overwritten. See pocketdock.yaml for project configuration.

[container]
id = "a1b2c3d4e5f6..."        # Podman container ID
name = "pd-a1b2c3d4"           # Podman container name (matches pocketdock.instance label)
image = "pocketdock/agent"
profile = "agent"
project = "my-widget"           # matches pocketdock.project label
created_at = "2026-02-05T09:15:00Z"
persist = true

[resources]
mem_limit = "256m"
cpu_percent = 50
network = false

[provenance]
# Which process/script created this container
created_by = "python llm_agent.py"   # best-effort: argv of the calling process
pid = 48291

[volumes]
"/home/sandbox/data" = "/home/alice/my-widget/.pocketdock/instances/pd-a1b2c3d4/data"
```

### What local instance data adds beyond Podman labels

Podman labels identify containers and their project assignment. Local instance data under `.pocketdock/instances/` stores what labels can't:

- **Command history** (`history.jsonl`): greppable timeline of every command, exit code, and duration.
- **Full stream logs** (`logs/`): complete output of every operation, timestamped. When an agent does something unexpected, you can replay exactly what happened.
- **Provenance** (`instance.toml`): which process created the container and when. Machine-generated, not for human editing.
- **Persistent workspace** (`data/`): automatically volume-mounted if it exists. Survives container stop/start.
- **Browsable structure**: `ls .pocketdock/instances/` shows what containers belong to this project.

### Persistence Management API

```python
from pocketdock import (
    list_containers,
    resume_container,
    destroy_container,
    prune,
)

# List all pocketdock containers on this machine (queries Podman labels)
for c in list_containers():
    print(f"{c.project}/{c.name}  {c.status}  {c.image}  {c.created_at}")

# List containers in a specific project
for c in list_containers(project="my-widget"):
    print(c.name, c.status)

# Resume a stopped container (works from anywhere — Podman name is machine-wide)
container = resume_container("stm32-dev")

# Destroy a container (removes instance directory too)
destroy_container("stm32-dev")   # asks confirmation if persist=True

# Clean up all stopped pocketdock containers
prune()                          # all projects
prune(project="my-widget")       # just one project
```

All pocketdock containers are labeled with `pocketdock.managed=true` and `pocketdock.project=<n>` so they can be identified without interfering with other containers on the system. Podman labels are the source of truth for container identity; local `.pocketdock/instances/` directories store history and working data.

### Ephemeral containers leave no trace

When `persist=False` (the default), no instance directory is created. No logs, no history, no metadata on disk. The container is created, used, destroyed — same as llm-sandbox. This is the clean path for agent sandboxing where you don't need post-hoc forensics.

Instance directories are only created for persistent containers (`persist=True`), where you explicitly want data to survive across sessions.

---

## File Structure

```
pocketdock/
├── README.md                           # Zero-to-running quickstart, badges, feature overview
├── LICENSE                             # BSD-2-Clause, (c) deftio llc
├── CHANGELOG.md                        # Keep-a-changelog format, updated every PR
├── CONTRIBUTING.md                     # Dev setup, workflow, quality bar (extracted from spec)
├── pyproject.toml                      # Package config + all tool configs (ruff, mypy, pytest, coverage, bandit)
├── uv.lock                             # uv lockfile (deterministic installs)
├── .python-version                     # 3.12 (default for development)
├── .pre-commit-config.yaml             # Git hooks: ruff, mypy, bandit, check-manifest
├── mkdocs.yml                          # Docs site config (mkdocs-material)
├── .github/
│   └── workflows/
│       ├── ci.yml                      # Lint + test matrix (3.10-3.13) + audit
│       └── docs.yml                    # Build and deploy docs to GitHub Pages
│
├── plan/                               # Project planning (this spec lives here)
│   ├── spec.md                         # ← THIS DOCUMENT — full architecture and design spec
│   ├── milestones.md                   # Milestone breakdown with acceptance criteria
│   └── decisions.md                    # Architectural decision log (optional: can stay in spec)
│
├── docs/                               # mkdocs-material source → GitHub Pages
│   ├── index.md                        # Home — same content as README.md
│   ├── quickstart.md                   # Detailed getting started guide
│   ├── concepts/
│   │   ├── architecture.md             # How pocketdock talks to Podman
│   │   ├── connection-model.md         # Connection-per-operation, async core
│   │   ├── output-model.md             # Buffer, callbacks, logging, how they compose
│   │   ├── sessions.md                 # Persistent shell vs run()
│   │   └── persistence.md             # 4 levels, project-rooted instance data
│   ├── guides/
│   │   ├── llm-agent.md               # Build an agent with sandboxed code execution
│   │   ├── embedded-dev.md            # Arduino/ESP32/STM32 workflow
│   │   ├── local-llm.md              # Run inference in a container
│   │   └── offline-setup.md           # Air-gapped environment setup
│   ├── reference/
│   │   ├── api.md                      # Full SDK API reference
│   │   ├── cli.md                      # All CLI commands
│   │   ├── config.md                   # pocketdock.yaml / instance.toml reference
│   │   └── errors.md                   # Error types and recovery
│   └── contributing.md                 # Mirrors CONTRIBUTING.md
│
├── images/
│   ├── minimal/
│   │   └── Dockerfile                  # Alpine + Python
│   ├── dev/
│   │   └── Dockerfile                  # Debian + tools
│   ├── agent/
│   │   └── Dockerfile                  # Debian + Python libs
│   └── embedded/
│       └── Dockerfile                  # Alpine + GCC/CMake/ARM toolchain
│
├── python/
│   └── pocketdock/
│       ├── __init__.py                 # sync public exports (default)
│       ├── py.typed                    # PEP 561 marker for mypy
│       ├── async_.py                   # async public exports
│       ├── _async_container.py         # AsyncContainer (the real implementation)
│       ├── _sync_container.py          # Container (sync facade over AsyncContainer)
│       ├── _socket_client.py           # async raw HTTP-over-Unix-socket client
│       ├── _stream.py                  # stream demux, chunked encoding, output capping
│       ├── _process.py                 # detached Process handle
│       ├── _buffer.py                  # ring buffer for output accumulation
│       ├── _session.py                 # persistent shell Session
│       ├── _callbacks.py               # callback registry and dispatch
│       ├── _logger.py                  # automatic stream-to-disk logger
│       ├── pool.py                     # ContainerPool
│       ├── persistence.py              # resume, snapshot, list, prune
│       ├── projects.py                 # .pocketdock/ dir management, pocketdock.yaml parsing, instance dirs
│       ├── profiles.py                 # image name resolution
│       ├── errors.py                   # ContainerNotRunning, ContainerGone, etc.
│       ├── types.py                    # ExecResult, ContainerInfo, StreamChunk, SessionResult
│       ├── _config.py                  # config loading, log level, structured operational logging
│       └── cli/
│           ├── __init__.py
│           ├── main.py                 # click group + top-level commands
│           ├── commands/
│           │   ├── init.py              # pocketdock init — create .pocketdock/pocketdock.yaml
│           │   ├── build.py
│           │   ├── create.py
│           │   ├── run.py
│           │   ├── list.py
│           │   ├── info.py
│           │   ├── shell.py
│           │   ├── logs.py             # logs, history viewing
│           │   ├── doctor.py           # orphan detection, stale cleanup, disk usage
│           │   ├── persistence.py      # stop, resume, shutdown, snapshot, prune
│           │   ├── systemd.py          # generate systemd user unit for persistent containers
│           │   └── images.py           # export, import
│           └── formatters.py           # rich output formatting
│
├── tests/
│   ├── test_socket_client.py           # connection, demux, error handling
│   ├── test_container_sync.py          # sync facade
│   ├── test_container_async.py         # async core
│   ├── test_concurrent.py             # multi-container, gather, threads
│   ├── test_streaming.py              # stream mode, detach mode, cancellation
│   ├── test_buffer.py                 # ring buffer, overflow, read/peek/drain
│   ├── test_callbacks.py              # on_stdout, on_stderr, on_exit, multi-container
│   ├── test_session.py               # persistent shell, send, sentinel parsing
│   ├── test_logger.py                # automatic stream logging, rotation, retention
│   ├── test_error_handling.py         # dead containers, gone containers, timeouts
│   ├── test_pool.py
│   ├── test_persistence.py
│   ├── test_projects.py
│   └── test_cli.py
│
├── examples/                               # All learning material lives here
│   ├── README.md                           # Index: Python SDK, CLI, templates — where to start
│   │
│   │  # ===== Python SDK examples =====
│   │  # --- Getting started ---
│   ├── 01_hello_world.py                   # Minimal: create, run, shutdown
│   ├── 02_run_python_code.py               # Execute Python, read stdout/stderr
│   ├── 03_file_operations.py               # push, pull, write_file, read_file
│   ├── 04_resource_limits.py               # Memory/CPU caps, what happens on OOM
│   ├── 05_context_manager.py               # Auto-cleanup with `with` statement
│   │
│   │  # --- Output model ---
│   ├── 10_streaming_output.py              # stream=True for long builds
│   ├── 11_detached_process.py              # Background server, check later
│   ├── 12_output_buffer.py                 # read(), peek(), buffer overflow
│   ├── 13_callbacks.py                     # on_stdout, on_stderr, on_exit
│   ├── 14_multi_container_callbacks.py     # One callback handling 5 containers
│   │
│   │  # --- Sessions ---
│   ├── 20_session_basics.py                # Persistent shell, cd/export persist
│   ├── 21_session_interactive.py           # Hand off to terminal
│   │
│   │  # --- Concurrency ---
│   ├── 30_async_basic.py                   # await c.run() with asyncio
│   ├── 31_async_gather.py                  # Run in 5 containers simultaneously
│   ├── 32_sync_threads.py                  # ThreadPoolExecutor pattern
│   │
│   │  # --- Persistence ---
│   ├── 40_persist_and_resume.py            # Stop, resume next day
│   ├── 41_volume_mounts.py                 # Host directory survives container
│   ├── 42_snapshot_and_restore.py          # Commit → new image → new container
│   │
│   │  # --- Real-world patterns ---
│   ├── 50_llm_agent_loop.py               # LLM generates code → run → feed back
│   ├── 51_code_evaluation.py              # Grade student code submissions
│   ├── 52_web_scraping_agent.py           # Agent scrapes in sandbox, no host risk
│   ├── 53_data_analysis.py                # Pandas/numpy in sandbox, pull CSV out
│   ├── 54_fastapi_server.py               # Run FastAPI in container, hit from host
│   ├── 55_local_llm_inference.py          # llama-cpp server in container, query it
│   ├── 56_embedded_arduino.py             # Compile Arduino sketch, pull .bin
│   ├── 57_embedded_esp32_platformio.py    # PlatformIO build for ESP32
│   ├── 58_cross_compile_arm.py            # ARM firmware compilation
│   ├── 59_ci_test_runner.py               # Run test suite in clean container
│   │
│   │  # --- Advanced ---
│   ├── 60_custom_image.py                 # Build and use your own Dockerfile
│   ├── 61_device_passthrough.py           # USB device for flashing hardware
│   ├── 62_pool_benchmark.py              # Measure pool vs cold-start latency
│   ├── 63_error_handling.py              # ContainerNotRunning, ContainerGone, recovery
│   │
│   │  # ===== CLI examples (shell scripts) =====
│   ├── cli/
│   │   ├── README.md                      # CLI examples index, prerequisites
│   │   ├── 01_hello_world.sh              # pocketdock create → run → shutdown
│   │   ├── 02_run_python.sh               # pocketdock run CONTAINER "python -c ..."
│   │   ├── 03_file_operations.sh          # pocketdock push/pull
│   │   ├── 04_resource_limits.sh          # pocketdock create --mem 128m --cpu 25
│   │   ├── 05_streaming.sh                # pocketdock run --stream CONTAINER "make all"
│   │   ├── 06_persistence.sh              # pocketdock create --persist → stop → resume → snapshot
│   │   ├── 07_project_workflow.sh         # pocketdock init → create --persist → list → status
│   │   ├── 08_embedded_build.sh           # Full embedded workflow: create, push, compile, pull
│   │   ├── 09_logs_and_history.sh         # pocketdock logs CONTAINER --history / --last 5
│   │   └── 10_full_lifecycle.sh           # Complete demo: build → create → run → push → pull → snapshot → export
│   │
│   │  # ===== Project templates (copy and modify) =====
│   └── templates/
│       ├── README.md                           # How to use templates
│       ├── llm-agent/                          # Template: LLM agent with sandboxed code execution
│       │   ├── README.md
│       │   ├── agent.py                        # Minimal agent loop (works with any LLM API)
│       │   ├── pocketdock.yaml                # Pre-configured project settings
│       │   └── prompts/
│       │       └── system.txt                  # System prompt with sandbox usage instructions
│       ├── data-pipeline/                      # Template: Process untrusted data in isolation
│       │   ├── README.md
│       │   ├── pipeline.py
│       │   └── Dockerfile.custom               # Extends agent profile with specific libs
│       ├── microservice/                       # Template: Run a web service in a container
│       │   ├── README.md
│       │   ├── app.py                          # FastAPI app
│       │   ├── client.py                       # Hit the service from the host
│       │   └── Dockerfile.web                  # Extends dev profile with uvicorn/fastapi
│       ├── embedded-firmware/                  # Template: Arduino/ESP32/STM32 dev workflow
│       │   ├── README.md
│       │   ├── build.py                        # Cross-compile, test, pull binary
│       │   └── platformio.ini                  # Example PlatformIO config
│       ├── local-llm/                          # Template: Local LLM inference in a container
│       │   ├── README.md                       # Honest guide: what works, what doesn't
│       │   ├── server.py                       # llama-cpp-python OpenAI-compatible server
│       │   ├── query.py                        # Hit the server from the host
│       │   └── Dockerfile.llm                  # Extends agent profile with llama-cpp-python
│       ├── dev-sandbox/                        # Template: Disposable dev environment
│       │   ├── README.md
│       │   └── setup.sh                        # One-command dev sandbox with dotfiles
│       └── multi-agent/                        # Template: Multiple agents, each in own container
│           ├── README.md
│           ├── orchestrator.py                 # Spawn N agents, collect results
│           └── callbacks_demo.py               # Real-time monitoring via callbacks
```

---

## Templates and Examples

pocketdock ships with two kinds of learning material: **templates** and **examples**. They serve different purposes.

### Templates: complete starting points

A template is a working project directory you copy and modify. Each one has its own README, is self-contained, and demonstrates a real workflow end-to-end.

**`examples/templates/llm-agent/`** — The most common use case. A minimal agent loop that generates code with any LLM API, executes it in a pocketdock container, reads the result, and feeds it back. Includes a system prompt that teaches the LLM about the sandbox's capabilities and constraints. Works with OpenAI, Anthropic, local models — no framework dependency.

**`examples/templates/data-pipeline/`** — Process untrusted data (uploaded CSVs, scraped HTML, user-provided scripts) in isolation. Shows how to push files in, run analysis, pull results out, and destroy the container. Includes a custom Dockerfile that extends the agent profile.

**`examples/templates/microservice/`** — Run a FastAPI app inside a pocketdock container with networking, port mapping, and detached mode. Query it from the host. Shows the pattern for containerized services that your code talks to — useful for sandboxing any server component, not just web apps.

**`examples/templates/embedded-firmware/`** — Create a persistent embedded dev container, install Arduino/PlatformIO platforms, compile firmware, pull the binary back to the host for flashing. Shows the full workflow from `pocketdock build` to `esptool.py write_flash`.

**`examples/templates/local-llm/`** — Run a small language model (Qwen2.5-0.5B) inside a persistent container using llama-cpp-python's OpenAI-compatible server. Shows persistent containers, volume mounts for model files, resource allocation, and the detached + callback pattern. README is honest about limitations: CPU-only is slow, this demonstrates pocketdock capabilities, not a production inference setup.

**`examples/templates/dev-sandbox/`** — One-command disposable dev environment. Run `pocketdock shell dev` and you're in a container with git, curl, vim, Python, and your dotfiles synced in. When you're done, it's gone.

**`examples/templates/multi-agent/`** — Orchestrate multiple agents, each in its own container, running simultaneously. Shows the async pattern with `asyncio.gather`, callbacks for real-time monitoring, and results aggregation. The canonical example of why the connection model matters.

### Examples: focused, single-concept demonstrations

Each example is a single file that demonstrates one thing. Numbered for reading order. Every example:

- Runs standalone (`python examples/01_hello_world.py` or `bash examples/cli/01_hello_world.sh`)
- Has a docstring/comments explaining what it demonstrates
- Handles cleanup even on error
- Is under 50 lines (with comments)

**Two paths through the same concepts.** The Python SDK examples (root of `examples/`) show programmatic usage — this is what agent developers and library consumers use. The CLI examples (`examples/cli/`) show the same workflows using the `pocketdock` command — this is what terminal users, scripters, and people evaluating the tool use.

Not every concept has both: callbacks, async, sessions, and pools are SDK-only. CLI examples cover the getting-started workflow, persistence, projects, logs, and complete lifecycle demos.

The numbering groups Python examples by concept: 01-05 (basics), 10-14 (output model), 20-21 (sessions), 30-32 (concurrency), 40-42 (persistence), 50-59 (real-world patterns), 60-63 (advanced). CLI examples are numbered 01-10 and cover a progression from first-touch to full lifecycle. You can skip around — each example is independent.

Notable examples worth calling out:

**`54_fastapi_server.py`** — Runs a FastAPI server inside a container with networking enabled, detached mode, and callbacks watching the server log. Queries it from the host with `httpx`. Demonstrates port mapping, detached processes, and the "container as a service" pattern. Every developer understands a web server.

**`55_local_llm_inference.py`** — Runs `llama-cpp-python` server inside a persistent container with a small model (~500MB Qwen2.5-0.5B Q4). Demonstrates persistent containers (install once, keep), volume mounts (model files are large, mount from host), resource limits (LLMs need RAM), and detached + callback pattern. **Honest caveat in the example:** CPU-only inference is slow (~10 tok/s for 0.5B). This is a "look what's possible" demo, not a production setup. For real local LLM use, point users at Ollama/llama.cpp directly. The example's value is showing pocketdock's capabilities, not replacing dedicated inference tools.

**`cli/10_full_lifecycle.sh`** — The CLI equivalent of "read this one script to understand the whole tool." Builds images, creates a persistent container, runs commands, pushes/pulls files, checks logs, snapshots, exports, and cleans up. Someone can copy-paste this into a terminal in 5 minutes and see everything pocketdock does.

The `examples/README.md` is an index with one-line descriptions and prerequisites (which image profile each example needs). It explicitly tells people: "If you prefer Python, start with `01_hello_world.py`. If you prefer the terminal, start with `cli/01_hello_world.sh`."

### Why templates, SDK examples, and CLI examples?

Three entry points for three types of users. **Templates** answer "how do I build X with pocketdock?" — they're project scaffolding for someone who knows what they want. **Python SDK examples** answer "how does feature Y work in code?" — they're reference material for library consumers. **CLI examples** answer "how do I use this from my terminal?" — they're for people who want to evaluate, script, or use pocketdock without writing Python.

A new user picks their path: reads `01_hello_world.py` or `cli/01_hello_world.sh` first, then copies `examples/templates/llm-agent/` to start their project, then refers back to specific examples when they need streaming, callbacks, or persistence.

---

## Competitive Landscape

Being honest about what already exists:

### `llm-sandbox` (vndee/llm-sandbox)

The most direct competitor. 100k+ downloads on PyPI, actively maintained, supports Docker/Podman/Kubernetes. Has container pools, security policies, artifact capture, MCP server, and IPython-based interactive sessions. Integrates with LangChain, LlamaIndex, OpenAI.

**Where it overlaps with pocketdock:** Container creation, code execution, stdout/stderr capture, resource limits, pools, Podman support.

**Where pocketdock is different:**

| Concern | llm-sandbox | pocketdock |
|---|---|---|
| Dependencies | `docker-py` or `podman-py` or `kubernetes` | Zero (stdlib socket client) |
| Offline-first | Not a design goal | Core principle — pre-built images, no runtime pulls |
| Image management | Uses stock images, installs at runtime | Ships Dockerfiles, builds once, works offline |
| Embedded/C++ | No | Dedicated profile with ARM, Arduino CLI, PlatformIO |
| Project organization | None | Project-rooted `.pocketdock/` with provenance, history |
| Output model | stdout/stderr, basic streaming | Ring buffer + callbacks + detached processes + sessions |
| CLI | None (library + MCP server) | First-class, `click` + `rich` |
| Persistence model | `commit_container` flag | 4 levels with metadata, export/import |
| Session model | IPython kernel (Python-only, heavy) | Raw shell with sentinel parsing (any language) |
| Philosophy | LLM-framework integration hub | Framework-agnostic standalone tool |

### Others

**E2B, Daytona, Modal** — Cloud platforms. Require API keys, internet, paid tiers. Different category entirely.

**`ai-code-sandbox`** (typper-io) — Small, Docker-only, minimal. Not actively maintained.

**`cohere-terrarium`** — Pyodide-based (WebAssembly), designed for GCP Cloud Run. Not for local use.

### Where pocketdock sits

`llm-sandbox` is a good library for "run LLM-generated Python in a Docker container." If that's your only need and you want something that works today with LangChain, it's the right choice.

pocketdock is a broader tool: a local container management library + CLI that's designed for offline use, embedded development, persistent workspaces, and project organization — and also happens to be excellent for LLM agent sandboxing. The zero-dependency socket client, the offline architecture, the embedded profile, and the project system are things `llm-sandbox` doesn't do and likely won't — they're solving different problems.

You're not reinventing the wheel. You're building a different vehicle.

---

## Who Wants This

In priority order by audience size and fit:

**1. LLM agent developers who run generated code.** The largest audience. These people are currently using `llm-sandbox`, raw `docker-py`, or nothing (YOLO-ing code execution on the host). pocketdock's pitch: zero dependencies (no more `pip install docker` breaking), offline-first (agents on laptops without reliable internet), and the output model (buffer + callbacks for real-time agent feedback loops). The `examples/templates/llm-agent/` is their entry point.

**2. Solo developers who want disposable environments.** "I need a clean Python to test something without polluting my system." Currently: `docker run -it python:3.12 bash` with manual volume mounts and no persistence. pocketdock makes this `pocketdock shell dev` with automatic cleanup, project organization, and session logging. Smaller audience, high per-person value.

**3. Embedded developers who cross-compile.** Arduino/ESP32/STM32 developers who want reproducible build environments. Currently: custom Dockerfiles cobbled together from Stack Overflow, no tooling. pocketdock's embedded profile with USB passthrough is genuinely unique. Small audience, zero competition.

**4. Education and code evaluation.** Teachers, bootcamps, interview platforms that need to run untrusted student code safely. They need sandboxing, resource limits, timeout, output capture — all core pocketdock features. Usually they build this from scratch with raw Docker. Small-to-medium audience, real willingness to adopt.

**5. Local CI/testing.** Run test suites in clean containers before pushing. Overlaps with GitHub Actions etc., but pocketdock's snapshot model (freeze a known-good environment, spin up fresh per test run) is useful for local pre-commit workflows or self-hosted runners.

**Where adoption starts:** Tiers 1 and 2 are volume. Tier 3 is passion (you). Tiers 4 and 5 happen organically once the tool exists and has good examples. The README should lead with Tier 1 (agent sandbox), show Tier 2 (dev sandbox) as the second example, and link to the embedded profile for Tier 3.

---

## Resolved Decisions

Summarizing the choices made:

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | SDK transport | Raw HTTP over Unix socket (stdlib only) | Zero deps, maximum portability, same protocol for Podman and Docker |
| 2 | CLI | Python, `click` + `rich` | Best CLI libraries, universal availability, shares code with SDK |
| 3 | Primary engine | Podman (Docker supported) | Rootless, daemonless, better security posture |
| 4 | `container.info()` | Point-in-time polled snapshot | Simple, user controls frequency, no streaming complexity for v1 |
| 5 | `container.update()` | Removed — use `run()` directly | Least magic. `run("pip install flask")` is clearer than `update(pip=["flask"])` |
| 6 | Streaming output | `run(stream=True)` → async iterator | Async HTTP model, essential for long-running agent tasks |
| 7 | Instance data | Project-rooted `.pocketdock/instances/` directory | Instance data lives next to the code it belongs to, not in a global registry. Projects can see, manage, and quota container data. No `~/.pocketdock/projects/`. |
| 8 | Organization | Project directory with `pocketdock.yaml` | `pocketdock init` creates `.pocketdock/pocketdock.yaml`. pocketdock walks up from cwd to find it (like `.git/`). Project name defaults to directory name. |
| 9 | Bun/TS SDK | Deferred | One language, one codebase. Can be ported later if there's actual demand from JS/TS consumers. |
| 10 | Concurrency | Async core, sync facade | Async is the natural fit for socket I/O. Sync wrapper for the 80% case. Users choose. |
| 11 | Connections | One per operation, not shared | Unix sockets are free. Isolation prevents streaming/detach from blocking other ops. |
| 12 | Container death | `ContainerNotRunning` / `ContainerGone` exceptions | Actionable errors. Other containers never affected. No cached state — always poll live. |
| 13 | Output buffering | Ring buffer per operation (1MB default) + callbacks | Buffer and callbacks get independent copies. Neither drains the other. Pull and push coexist. |
| 14 | Sessions | Persistent shell via long-lived exec + sentinel parsing | `run()` for isolated calls, `session()` for stateful shell. Both coexist on same container. |
| 15 | Stream logging | Automatic per-operation log files + JSONL history | On by default. Buffer/callbacks/logs are independent copies. Configurable rotation and retention. |
| 16 | Test coverage | 100% line coverage, no `# pragma: no cover` | ~800 lines of library code means every line is reachable. If a line can't be tested, it shouldn't exist. TDD — tests first, implementation to match. |
| 17 | Test strategy | No mocks — integration tests against real Podman | Mocking the socket would test the mock, not the code. The bugs that matter only surface against a real engine. Podman available in GitHub Actions Ubuntu runners. |
| 18 | Linting | `ruff check` + `ruff format` + `mypy --strict` + `bandit` | All configured in `pyproject.toml`. Enforced by pre-commit hooks and CI. Zero warnings, zero exceptions. |
| 19 | Git workflow | Feature branches → PR → CI → merge to main → tag | Branch protection on main. No direct pushes. CI must pass before merge. Tag triggers PyPI publish. |
| 20 | Versioning | Semver. 0.x for milestones, 1.0.0 after M9 | 0.x releases have no API stability promise. 1.0 means stable API. M10 (pool) is post-1.0. |
| 21 | License | BSD-2-Clause, (c) deftio llc | Simple, permissive, no patent/NOTICE complexity. SPDX header in every source file. |
| 22 | Project tooling | `uv` for venvs, deps, lockfile, commands | Mandated. Single tool for Python version management, virtual environments, dependency resolution, and command execution. |
| 23 | Documentation | mkdocs-material → GitHub Pages | Mandated. Renders markdown to HTML. Builds in CI, deploys on merge to main. Does not author content — content accuracy is enforced by dev cycle step 7. |
| 24 | Python version | 3.10+ | 3.9 EOL Oct 2025. 3.10 gives union types, match, better errors. `tomllib` still needs fallback (3.11+). |
| 25 | Long-running containers | Lifecycle management yes, process supervision no | `list`, `stop --all`, `info`, `logs --follow` for management. Idle timeout as optional config. `pocketdock systemd` generates unit files but doesn't manage systemd. Auto-restart, health checks, start-on-boot are out of scope. |
| 26 | Container discovery | Podman labels (identity) + project-local instance data (history) | `pocketdock.*` OCI labels including `data-path`. `pocketdock list` queries labels, scopes to current project by default, `--all-projects` for machine-wide. No global registry. |
| 27 | `pocketdock doctor` | Report-only by default, `--fix` to act | Reconciles labels against project-local instance dirs (using `pocketdock.data-path` label). Scoped to current project. `--fix` creates missing dirs, removes stale ones. Cannot fix port conflicts (user decision). |
| 28 | Config file format | YAML for human-authored config, TOML for machine-generated metadata | `pocketdock.yaml` is hierarchical, supports comments, humans edit it. `instance.toml` is flat, machine-generated, auto-commented "do not edit." PyYAML is a CLI dependency. SDK stays zero-dep. |
| 29 | Ephemeral containers | Leave no trace on disk | `persist=False` (default) creates no instance directory, no logs, no metadata. Same clean model as llm-sandbox. Instance dirs only for persistent containers. |

---

## Open Questions (Remaining)

1. **Embedded profile scope.** The `embedded` profile currently includes ARM cross-compiler from Alpine repos. Should it also include ESP-IDF, AVR, RISC-V? These are large and specialized. Recommendation: keep base lean (GCC + ARM), document extending for specific targets.

2. **Multi-architecture support.** Should pocketdock images be built for both amd64 and arm64? Relevant for Apple Silicon Macs. Podman handles this via QEMU but native is faster. Recommendation: document `podman build --platform linux/arm64`, don't mandate multi-arch.

3. **Session sentinel reliability.** Sessions detect command completion by appending `echo __PD_SENTINEL_$?__` after each command and scanning output for it. This breaks if the command itself outputs the sentinel string, or if the command reads all of stdin (consuming the sentinel). Alternative approaches: use a unique per-command UUID in the sentinel, or use a side-channel (write exit code to a temp file and poll it). Recommendation: UUID-based sentinel for v1, document the edge cases, revisit if it's a real problem.

4. **Log storage for high-volume agents.** An agent running 1000 `run()` calls per hour generates 1000 log files. The `max_logs_per_instance` cap handles this, but should there be an optional mode that batches multiple runs into a single log file per time window (e.g., one log per hour)? Recommendation: per-run files for v1, add batching if disk I/O becomes a real problem.

---

## Dependencies

| Component | License | Required? | Notes |
|---|---|---|---|
| Podman or Docker | Apache 2.0 | Yes (one of them) | Pre-installed by user |
| Python 3.10+ | PSF | Yes | Pre-installed on most systems |
| `click` | BSD-3 | Yes (CLI only) | CLI framework |
| `rich` | MIT | Yes (CLI only) | Pretty output |
| `PyYAML` | MIT | Yes (CLI only) | Config file parsing (`pocketdock.yaml`) |

**SDK dependencies**: 0 (stdlib only: `http.client`, `json`, `socket`, `tarfile`)
**CLI dependencies**: 3 (`click`, `rich`, `PyYAML`)
**Conditional**: `tomli` for Python 3.10 only (`tomllib` is in stdlib 3.11+) — used for reading machine-generated `instance.toml`, not the core SDK

**Dev dependencies** (not shipped to users):

| Tool | Purpose |
|---|---|
| `pytest` | Test runner |
| `pytest-cov` | Coverage reporting, enforced at 100% |
| `pytest-asyncio` | Async test support |
| `ruff` | Linting + formatting (replaces flake8, isort, black) |
| `mypy` | Static type checking, strict mode |
| `bandit` | Security linting |
| `pre-commit` | Git hooks for all of the above |
| `check-manifest` | Verify sdist/wheel completeness |
| `pip-audit` | Dependency vulnerability scanning (for click, rich) |
| `mkdocs-material` | Documentation site generation and GitHub Pages deployment |

---

## Development and Contributing

### Philosophy

This is an ~800-line library that talks directly to a Unix socket. Every line matters. The quality bar is:

- **100% line coverage.** No `# pragma: no cover`. No exclusions. If a line can't be tested, it shouldn't exist.
- **No mocks.** Tests run against a real Podman instance. The entire value of this library is that the socket client works correctly — mocking it would test the mock, not the code. Podman is pre-installed on GitHub Actions Ubuntu runners, so this is viable in CI.
- **100% ruff clean.** `ruff check` and `ruff format` with zero warnings, zero exceptions. Configured once in `pyproject.toml`, enforced by pre-commit and CI.
- **`mypy --strict` clean.** Every function has type annotations. Every return type is explicit. Strict mode from day one — retrofitting it later is miserable.
- **`bandit` clean.** This tool handles Unix sockets, file I/O, subprocess-adjacent operations, and tar archives. Security linting catches the classes of bugs that matter here.

### Test strategy

All tests are integration tests against a real Podman socket. No mocks, no fakes, no stubs.

**Why no mocks?** The library's job is to send HTTP requests over a Unix socket and correctly parse the responses. If you mock the socket, you're testing string construction, not actual communication. The bugs that matter — malformed headers, incorrect stream demux, tar encoding edge cases, Podman vs Docker behavioral differences — only surface against a real engine. Mocks would give false confidence.

**Test speed.** Container operations take real time. Mitigate this by:

- Using the `minimal` profile (~25MB, starts in <500ms)
- Sharing a single container across related tests where state doesn't matter (read-only operations)
- Creating fresh containers only when the test mutates state
- Parallelizing test files with `pytest-xdist` if wall-clock time becomes a problem (not expected at ~800 lines)

**What if Podman isn't available?** Tests skip gracefully with `pytest.mark.skipif` if no socket is found. This lets someone run `ruff` and `mypy` checks locally without Podman installed. But full CI always has Podman — tests that skip locally must pass in CI.

**Test organization mirrors the source:**

| Test file | What it covers | Needs Podman? |
|---|---|---|
| `test_socket_client.py` | Raw connection, ping, HTTP parsing, demux | Yes |
| `test_container_sync.py` | Sync facade: run, info, reboot, shutdown | Yes |
| `test_container_async.py` | Async core: await run, gather, concurrent | Yes |
| `test_concurrent.py` | Multi-container independence, one dying doesn't affect others | Yes |
| `test_streaming.py` | stream=True, detach=True, cancellation | Yes |
| `test_buffer.py` | Ring buffer: read, peek, overflow, drain | No (pure data structure) |
| `test_callbacks.py` | on_stdout, on_stderr, on_exit, multi-container dispatch | Yes |
| `test_session.py` | Persistent shell, send, sentinel parsing, state persistence | Yes |
| `test_logger.py` | Stream-to-disk logging, rotation, retention, JSONL history | Yes |
| `test_error_handling.py` | ContainerNotRunning, ContainerGone, timeout, recovery | Yes |
| `test_pool.py` | Pre-warming, acquire/release, pool exhaustion | Yes |
| `test_persistence.py` | persist=True, resume, snapshot, volume mounts | Yes |
| `test_projects.py` | .pocketdock/ structure, pocketdock.yaml, instance.toml, provenance, prune | Partial (filesystem only for some) |
| `test_cli.py` | All CLI commands via click.testing.CliRunner | Yes |

### Automation tools

Everything runs through `pyproject.toml` configuration. No separate config files except `.pre-commit-config.yaml` (git hooks) and `.pocketdock/pocketdock.yaml` (project settings — not a dev tool config).

```toml
# pyproject.toml (relevant sections)

[tool.ruff]
target-version = "py310"
line-length = 99

[tool.ruff.lint]
select = ["ALL"]
ignore = ["D1"]  # don't require docstrings on every function (public API is documented in spec)

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.10"
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
addopts = "--cov=pocketdock --cov-report=term-missing --cov-fail-under=100 -v"

[tool.coverage.run]
branch = true
source = ["pocketdock"]

[tool.coverage.report]
fail_under = 100
show_missing = true
exclude_lines = []  # explicitly empty — no exclusions allowed

[tool.bandit]
exclude_dirs = ["tests"]
```

### Pre-commit hooks

Run automatically on every `git commit`. Catches problems before they reach CI.

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.14.0
    hooks:
      - id: mypy
        additional_dependencies: [click, types-click]

  - repo: https://github.com/PyCQA/bandit
    rev: 1.8.0
    hooks:
      - id: bandit
        args: [-c, pyproject.toml]

  - repo: https://github.com/mgedmin/check-manifest
    rev: "0.50"
    hooks:
      - id: check-manifest
```

### CI pipeline (GitHub Actions)

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy --strict python/pocketdock/
      - run: uv run bandit -r python/pocketdock/ -c pyproject.toml
      - name: Check license headers
        run: |
          find python/pocketdock -name '*.py' | while read f; do
            head -2 "$f" | grep -q 'SPDX-License-Identifier: BSD-2-Clause' || \
              (echo "Missing license header: $f" && exit 1)
          done

  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv python install ${{ matrix.python-version }}
      - run: uv sync --dev --python ${{ matrix.python-version }}
      - run: systemctl --user start podman.socket
      - run: podman build -t pocketdock/minimal images/minimal/
      - run: uv run pytest
        # pytest is configured in pyproject.toml to enforce 100% coverage

  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --dev
      - run: uv run mkdocs build --strict
        # --strict fails on warnings (broken links, missing pages)

  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --dev
      - run: uv run pip-audit
```

**CI must pass before merge.** Branch protection on `main`: require status checks (lint + test matrix + docs build + audit), require PR review, no direct pushes.

**Podman in CI.** Ubuntu runners have Podman pre-installed. `systemctl --user start podman.socket` activates the socket. Build the `minimal` image in CI (takes ~5 seconds from cached layers). All tests run against this real instance.

**Docs in CI.** `mkdocs build --strict` catches broken internal links, missing pages, and malformed markdown. If docs don't build cleanly, CI fails. This prevents doc drift.

### Git workflow

```
main (protected)
  │
  ├── feat/m0-socket-client        # feature branches named by milestone or topic
  ├── feat/m1-blocking-run
  ├── fix/stream-demux-padding
  ├── test/session-sentinel-edge
  └── docs/readme-quickstart
```

**Branch naming:** `{type}/{description}` where type is `feat`, `fix`, `test`, `docs`, `ci`, or `refactor`.

**Commit messages:** Conventional-ish. Prefix with type. Be specific.

```
feat: implement async socket client with Podman auto-detection
fix: handle chunked transfer encoding with zero-length chunks
test: add coverage for ContainerGone after external podman rm
docs: add FastAPI server example
ci: add Python 3.13 to test matrix
```

Not enforced by tooling (no commitlint), but followed by convention. The commit log should be readable as a narrative of what happened.

**Development cycle for each milestone:**

```
1. Create branch: feat/m{N}-{name}
2. Write test cases first (TDD)
3. Run tests — they fail (red)
4. Write implementation
5. Run tests — they pass (green)
6. Run full suite: ruff + mypy + bandit + pytest (everything green, 100% coverage)
7. Doc sync — READ and UPDATE content (mkdocs only builds, it doesn't verify accuracy):
     - Read the README. Does it still match current API and behavior?
     - Read affected docs/ pages. Do they reflect this change?
     - Run affected Python SDK examples. Do they still work?
     - Run affected CLI examples (examples/cli/). Do they still work?
     - Update CHANGELOG.md for this change.
     - Check all source files have the license header.
     - If this was an architectural change, update plan/spec.md.
     This is a content review, not a build step. `mkdocs build` renders markdown
     to HTML — it cannot tell you if the markdown is wrong. You have to read it.
8. Run full suite again (doc changes can break things)
9. Push branch, open PR
10. CI runs (lint + test matrix + audit + docs build)
11. CI passes → merge to main
12. Tag release if milestone is complete
```

Step 7 is the one everyone skips. Don't. Stale docs are worse than no docs — they actively mislead. Doing it inside the dev loop (not after) means the person who changed the code is the person updating the docs, while the context is fresh.

### Versioning and releases

**Semantic versioning (semver).**

- `0.x.y` — pre-1.0 releases. API may change between minor versions. Each milestone that reaches `main` gets a release.
- `1.0.0` — after M9 (all image profiles, CLI complete, export/import). API stability promise begins.
- `1.x.y` — post-1.0. Patch releases for bugs. Minor releases for backwards-compatible additions (like M10 Pool).

**Release mapping:**

| Milestone | Version | Notes |
|---|---|---|
| M0 (scaffold + socket client) | `0.1.0` | Repo live, docs live, CI green, socket client works |
| M1 (blocking run) | `0.2.0` | **First usable release** — agents can sandbox code |
| M2 (file ops) | `0.3.0` | |
| M3 (info + limits) | `0.4.0` | |
| M4 (stream/detach/buffer/callbacks) | `0.5.0` | |
| M5 (sessions) | `0.6.0` | **Good tool** |
| M6 (persistence) | `0.7.0` | |
| M7 (projects) | `0.8.0` | |
| M8 (CLI) | `0.9.0` | **Product** |
| M9 (image profiles) | `1.0.0` | **Stable API** |
| M10 (pool) | `1.1.0` | Post-stable extension |

**Release process:**

```
1. All tests pass locally (full suite)
2. PR merged to main
3. CI passes on main
4. Tag: git tag -a v0.2.0 -m "M1: blocking run with sync and async APIs"
5. Push tag: git push origin v0.2.0
6. GitHub Actions builds and publishes to PyPI (triggered by tag)
7. GitHub Release created with changelog excerpt
```

**No release without green CI. No tag without green CI. No exceptions.**

### Changelog

`CHANGELOG.md` in the repo root. Updated with every PR. Format follows [Keep a Changelog](https://keepachangelog.com/):

```markdown
# Changelog

## [Unreleased]

## [0.2.0] - 2026-xx-xx
### Added
- `Container` class with sync and async APIs
- `create_new_container()` factory
- Blocking `run()` with timeout and output capping
- `ContainerNotRunning` / `ContainerGone` error handling
- Context manager for automatic cleanup
- Socket auto-detection (Podman rootless → Podman system → Docker)

### [0.1.0] - 2026-xx-xx
### Added
- Project scaffold: README, CONTRIBUTING, docs site (GitHub Pages), CI pipeline
- BSD-2-Clause license with source file headers
- Async socket client over Unix socket
- HTTP/1.1 request/response over UDS
- Stream demultiplexing (Docker exec stream protocol)
- Tar archive packing/unpacking for file operations
- Podman and Docker socket auto-detection
```

### Project setup with `uv`

[`uv`](https://docs.astral.sh/uv/) is the project tool — it handles virtual environments, dependency resolution, lockfiles, and running commands. It's from Astral (same team as ruff), it's fast, and it replaces pip/pip-tools/virtualenv/poetry in a single binary.

**Initial scaffold:**

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create project
uv init pocketdock
cd pocketdock

# Set Python version
uv python pin 3.12

# Add runtime dependencies (CLI only — SDK has zero deps)
uv add --optional cli click rich pyyaml

# Add dev dependencies
uv add --dev pytest pytest-cov pytest-asyncio pytest-xdist \
    ruff mypy bandit \
    pre-commit check-manifest pip-audit \
    mkdocs-material mkdocs-material-extensions

# Install pre-commit hooks
uv run pre-commit install
```

**Daily development:**

```bash
# Run tests
uv run pytest

# Run linters
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict python/pocketdock/
uv run bandit -r python/pocketdock/ -c pyproject.toml

# Run everything (what CI does)
uv run pre-commit run --all-files && uv run pytest

# Build and serve docs locally
uv run mkdocs serve    # http://localhost:8000

# Build package
uv build
```

### Source file license headers

Every `.py` source file in `python/pocketdock/` must include this header:

```python
# Copyright (c) deftio llc
# SPDX-License-Identifier: BSD-2-Clause
```

Two lines. SPDX identifier is machine-readable. No boilerplate essay. `ruff` won't enforce this, but `pre-commit` can via a custom hook or a quick `grep` check in CI:

```yaml
# In ci.yml
- name: Check license headers
  run: |
    find python/pocketdock -name '*.py' | while read f; do
      head -2 "$f" | grep -q 'SPDX-License-Identifier: BSD-2-Clause' || \
        (echo "Missing license header: $f" && exit 1)
    done
```

Test files don't need the header — they're not distributed in the package.

### Documentation site (GitHub Pages)

Documentation is built with [mkdocs-material](https://squidfunk.github.io/mkdocs-material/) and deployed to GitHub Pages on every push to `main`. mkdocs renders markdown to HTML — it does not author or update content. Content accuracy is a manual step in the dev cycle (step 7).

**Docs structure:**

- `docs/index.md` — mirrors README (one source of truth, symlinked or generated)
- `docs/quickstart.md` — detailed getting started (install uv, install pocketdock, build images, run first container)
- `docs/concepts/` — architecture, connection model, output model, sessions, persistence (extracted from this spec)
- `docs/guides/` — task-oriented: build an LLM agent, set up embedded dev, run local LLM, air-gap setup
- `docs/reference/` — API reference, CLI commands, config files, error types
- `docs/contributing.md` — mirrors CONTRIBUTING.md

**Deployment:**

```yaml
# .github/workflows/docs.yml
name: Docs

on:
  push:
    branches: [main]

permissions:
  contents: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --dev
      - run: uv run mkdocs gh-deploy --force
```

**Docs are part of the dev cycle, not an afterthought.** Every PR that changes API surface, behavior, or configuration must update the corresponding docs. Step 7 of the dev cycle enforces this.

### Initial setup checklist

Before writing any code:

```
[ ] Create GitHub repo: deftio/pocketdock (or preferred namespace)
[ ] Initialize with LICENSE (BSD-2-Clause, (c) deftio llc), README.md, .gitignore
[ ] Set up branch protection on main (require PR, require CI, no force push)
[ ] Create milestone labels in GitHub Issues: M0 through M10
[ ] Create issue for each milestone with acceptance criteria from this spec
[ ] Set up project with uv:
    [ ] uv init, uv python pin 3.12
    [ ] pyproject.toml with all tool configs
    [ ] uv add dev dependencies
[ ] Set up .pre-commit-config.yaml + uv run pre-commit install
[ ] Set up .github/workflows/ci.yml
[ ] Set up .github/workflows/docs.yml
[ ] Create mkdocs.yml at repo root and docs/ directory with placeholder pages
[ ] Create plan/ directory, move this spec to plan/spec.md
[ ] Create images/minimal/Dockerfile
[ ] Create empty python/pocketdock/__init__.py with license header and py.typed
[ ] First commit: empty package structure with passing CI (zero tests, zero code, but lint/mypy/bandit/docs all clean)
[ ] Verify: push, CI runs, docs deploy, everything green on an empty project
[ ] Begin M0: create feat/m0-socket-client branch, write test_socket_client.py first
```

The first commit should have zero code and passing CI. This proves the automation works before any complexity is added. Every subsequent commit adds to a known-good state.

---

## What This Is Not

- **Not E2B / Daytona / Modal.** Those are cloud platforms. This is a local library + CLI.
- **Not a Docker wrapper framework.** No service definitions, no compose. `pocketdock.yaml` configures pocketdock itself (profiles, logging), not container orchestration.
- **Not testcontainers.** Similar energy, but testcontainers is for integration testing. This is for code execution sandboxing and dev environments.
- **Not a security product.** Container isolation is good enough for "my own LLM agent might generate bad code" but not for "adversarial users are trying to escape."

---

## Success Criteria

pocketdock is done when:

- [ ] `pip install pocketdock` gives you both library and CLI
- [ ] `create_new_container().run("print(1)").stdout == "1\n"` works
- [ ] SDK is zero-dependency (stdlib-only socket client)
- [ ] Works with Podman. Works with Docker. Auto-detects which.
- [ ] Works fully offline after initial image build
- [ ] Four image profiles build and work (minimal, dev, agent, embedded)
- [ ] `container.run()` / `.info()` / `.reboot()` / `.shutdown()` all work
- [ ] Sync and async APIs both work: `c.run()` and `await c.run()`
- [ ] Multiple containers from one process: independent, one dying doesn't affect others
- [ ] Streaming + blocking + detached can run simultaneously on the same container
- [ ] Output buffer: `proc.read()` / `proc.peek()` work, overflow handled gracefully
- [ ] Callbacks: `on_stdout` / `on_stderr` / `on_exit` fire in real-time, work across multiple containers
- [ ] Sessions: `c.session().send("cd /tmp && pwd")` returns `/tmp`, state persists across sends
- [ ] Persistence: `persist=True` → shutdown → `resume_container()` round-trips
- [ ] Persistence: `container.snapshot()` creates a reusable image
- [ ] Persistence: volume mounts and `.pocketdock/instances/` directory structure work
- [ ] Projects: `pocketdock init` creates config, containers scope to project, list/prune work
- [ ] CLI: all commands work, help is beautiful, destructive actions confirm
- [ ] CLI: `pocketdock export` / `import` works for air-gapped transfer
- [ ] Pool pre-warming reduces per-execution latency to <100ms
- [ ] Clean container cleanup on normal exit, crash, and KeyboardInterrupt
- [ ] Total library code under 1000 lines (excluding CLI)
- [ ] 100% line coverage in tests (`pytest --cov` with no exclusions)
- [ ] Zero mocks — all tests run against real Podman
- [ ] `ruff check` + `ruff format` clean with zero warnings
- [ ] `mypy --strict` clean
- [ ] `bandit` clean
- [ ] CI passes on Python 3.10, 3.11, 3.12, 3.13
- [ ] Pre-commit hooks configured and enforced
- [ ] CHANGELOG.md updated with every release
- [ ] Documentation site live on GitHub Pages, builds cleanly with `mkdocs build --strict`
- [ ] Every `.py` source file has BSD-2-Clause SPDX license header
- [ ] All Python SDK examples run successfully against real Podman
- [ ] All CLI examples (`examples/cli/*.sh`) run successfully
- [ ] `plan/spec.md` is current and matches implemented behavior
- [ ] README: zero to running in under 5 minutes

---

## Honest Assessment: Should You Build This?

### What's genuinely good about this project

**The problem is real.** Anyone building LLM agents that execute code rewrites the same container glue code. The pattern is always: create container, exec into it, demux the output stream, handle timeouts, clean up. It's 200-400 lines of fiddly code that everyone writes from scratch.

**The offline-first angle is differentiating.** E2B, Daytona, Modal — all cloud-first. If you're on a plane, behind a corporate firewall, or just philosophically opposed to sending your code to someone else's server, there's nothing good in this space. pocketdock would be the only serious option.

**Zero-dependency socket SDK is elegant.** Most people reach for `docker-py` without realizing the REST API is simple enough to talk to directly. The socket client is the kind of thing that, once written well, never needs to change. It's a genuine technical contribution.

**The embedded profile is a niche no one else serves.** E2B doesn't have GCC. Daytona doesn't have Arduino CLI. This is a real gap for embedded developers who want reproducible build environments.

**The project-rooted data model is thoughtful.** Being able to `ls .pocketdock/instances/` in a project and see what containers belong to it, who created them, and what ran inside them — that's the kind of thing that separates a tool you actually use from a tool you try once. Data lives next to the code it belongs to, not hidden in a global dot-directory.

### What's hard

**The socket client is the real work.** Raw HTTP over Unix sockets sounds simple until you're demultiplexing Docker's stream protocol, building tar archives in memory for file push, extracting them for file pull, handling chunked transfer encoding, and dealing with the subtle differences between Docker and Podman's API responses. This is ~400 lines of careful, tested code per language. It's the foundation everything else sits on, and if it has bugs, nothing works.

**Scope has grown significantly.** What started as "a Sandbox class" is now: a zero-dep socket client, a Container class with 4 execution modes, file operations via tar streams, a persistence system with 4 levels, a project-rooted instance data manager, a CLI with 15+ commands, 4 image profiles, and air-gap export/import. This is not a weekend project — but it's now a focused one without the distraction of maintaining two language implementations.

### Realistic effort

| Milestone | Relative difficulty | Cumulative value |
|---|---|---|
| M0 — Project scaffold + async socket client | 🔴 Hard (the foundation, async I/O, demux) | Repo, CI, docs site, and the core that everything builds on |
| M1 — Blocking run (sync + async) | 🔴 Hard (two facades, error model, multi-container) | **Usable** — agents can sandbox code |
| M2 — File operations | 🟡 Medium (tar streams) | Push code in, pull results out |
| M3 — Info + limits | 🟢 Easy | Monitoring and resource control |
| M4 — Stream/detach/buffer/callbacks | 🔴 Hard (concurrent conns, ring buffer, dispatch) | Full output model |
| M5 — Sessions | 🟡 Medium (sentinel parsing, TTY handoff) | **Good tool** — persistent shells, real workflows |
| M6 — Persistence | 🟡 Medium | State survives across sessions |
| M7 — Projects | 🟢 Easy (filesystem + YAML) | Organization and provenance |
| M8 — CLI | 🟡 Medium (15+ commands, polish) | **Product** — non-SDK users can use it |
| M9 — Image profiles | 🟢 Easy (Dockerfiles) | Breadth: embedded, agent, dev |
| M10 — Pool | 🟢 Easy | High-throughput optimization |

### The 80/20 path: milestones by functionality

Each milestone is usable on its own. Stop at any point and you have a working tool.

**M0 — Project scaffold + async socket client.**

Two parts. **Part A: scaffolding.** GitHub repo, LICENSE (BSD-2-Clause, © deftio llc), README.md with project overview and badges, CONTRIBUTING.md with dev setup instructions, docs/ site with mkdocs-material (deployed to GitHub Pages), empty examples/ directory with README, pyproject.toml with all tool configs, uv.lock, .pre-commit-config.yaml, CI pipeline (lint + test matrix + audit + docs deploy), branch protection on main. First commit: empty package, passing CI, live docs site. This is done before writing a single line of library code.

**Part B: async socket client.** The hard part. Async raw HTTP over Unix socket. `GET /_ping`, `POST /containers/create`, `POST /containers/{id}/start`, `POST /exec/{id}/start` with stream demux, `DELETE /containers/{id}`. Auto-detect Podman/Docker socket. Tested against real Podman. This is the foundation — if this is wrong, everything above it is wrong. Hardest milestone by far relative to its size.

**M1 — Container with blocking `run()` (sync + async).**
`AsyncContainer` with `await c.run("echo hello")`. Sync `Container` facade on top. `create_new_container()` → `container.run()` → `ExecResult` → `container.shutdown()`. Context manager. Timeout. Output capping. `ContainerNotRunning` / `ContainerGone` error handling. One image profile (minimal). Multiple containers from one process work independently. This is the point where it's useful.

**M2 — File operations.**
`push()`, `pull()`, `write_file()`, `read_file()`, `list_files()`. Tar archive packing/unpacking over the socket. This unlocks the pattern of pushing code in, running it, pulling results out.

**M3 — `info()` and resource limits.**
`container.info()` returns polled stats. Memory/CPU limits enforced at container creation. You can now monitor what your containers are doing.

**M4 — Streaming, detached, buffer, and callbacks.**
`run(stream=True)` as async iterator. `run(detach=True)` returns `Process` handle with ring buffer. `proc.read()` / `proc.peek()`. `c.on_stdout(fn)` / `c.on_stderr(fn)` / `c.on_exit(fn)` callback registration. Callbacks and buffer are independent copies — neither drains the other. This is the full output model.

**M5 — Sessions.**
`c.session()` opens a persistent shell connection. `session.send()`, `session.read()`, `session.on_output(fn)`, `session.interactive()` for TTY handoff. Sentinel-based command boundary detection. Sessions coexist with `run()` and detached processes on the same container.

**M6 — Persistence.**
`persist=True`, `resume_container()`, `snapshot()`, volume mounts. `list_containers()`, `destroy_container()`, `prune()`. You can now keep state across sessions.

**M7 — Projects and local data.**
`pocketdock init` creates `.pocketdock/pocketdock.yaml`. Instance directories under `.pocketdock/instances/` with `instance.toml` provenance and `history.jsonl`. Project-scoped listing and cleanup via Podman labels. `pocketdock doctor` for reconciliation. You can now manage multiple workstreams.

**M8 — CLI.**
`click` + `rich`. All commands. Beautiful help. Confirmations. Logging. This is the polish layer — everything under it already works via the SDK.

**M9 — Additional image profiles.**
`dev`, `agent`, `embedded` Dockerfiles. Arduino CLI + PlatformIO. `devices=[]` passthrough. `export` / `import` for air-gap. This is the breadth layer.

**M10 — Pool.**
`ContainerPool` with pre-warming. Only matters for high-throughput agent workloads where per-container startup latency is a bottleneck.

After M1 you have a tool. After M5 you have a good tool. After M8 you have a product. M9-M10 are extensions you build when you need them.

### Bottom line

The problem is real, the design is sound, and the niche — offline, zero-dep, embedded-friendly — is genuinely unserved. The socket client (M0) is the make-or-break piece: if that's solid, everything above it is straightforward. If you find yourself wanting to start with the CLI or the image profiles, resist — those are the fun parts, not the hard parts. M0 → M1 is the proof of concept. Everything else follows.