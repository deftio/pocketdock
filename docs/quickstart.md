# Quickstart

Get a container running in under a minute.

## Prerequisites

- **Python 3.10+**
- **Container engine**: [Podman](https://podman.io/getting-started/installation) (recommended) or [Docker](https://docs.docker.com/get-docker/)

## Install

```bash
pip install pocket-dock          # SDK only
pip install pocket-dock[cli]     # SDK + CLI
```

## Build the Minimal Image

pocket-dock ships Dockerfiles for four image profiles. The `minimal` profile (~25MB, <500ms startup) is the default:

```bash
pocket-dock build minimal
```

Or build directly with your container engine:

```bash
# Podman
podman build -t pocket-dock/minimal images/minimal/

# Docker
docker build -t pocket-dock/minimal images/minimal/
```

## Run Your First Container

```python
from pocket_dock import create_new_container

c = create_new_container()
result = c.run("echo hello")
print(result.stdout)   # "hello\n"
print(result.ok)       # True
c.shutdown()
```

## Context Manager

Use a context manager to automatically clean up the container:

```python
from pocket_dock import create_new_container

with create_new_container() as c:
    result = c.run("echo hello")
    print(result.stdout)
# Container is stopped and removed automatically
```

## Run Python Code

Use the `lang` parameter to run code in a specific language:

```python
with create_new_container() as c:
    result = c.run("print(2 + 2)", lang="python")
    print(result.stdout)  # "4\n"
```

## File Operations

Read and write files inside the container:

```python
with create_new_container() as c:
    c.write_file("/home/sandbox/hello.txt", "Hello from host!")
    data = c.read_file("/home/sandbox/hello.txt")
    print(data.decode())  # "Hello from host!"

    files = c.list_files("/home/sandbox/")
    print(files)  # ["hello.txt"]
```

## Try the CLI

```bash
# Create a persistent container
pocket-dock create --name my-sandbox

# Run a command
pocket-dock run my-sandbox echo hello

# Interactive shell
pocket-dock shell my-sandbox

# Clean up
pocket-dock shutdown my-sandbox --yes
```

## Next Steps

- **[Creating Containers](guide/containers.md)** — all parameters, resource limits, info, reboot
- **[Running Commands](guide/commands.md)** — blocking, streaming, and detached modes
- **[Sessions](guide/sessions.md)** — persistent shell sessions
- **[CLI Reference](cli.md)** — all 21 commands
