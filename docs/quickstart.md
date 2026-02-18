# Quickstart

Get a container running in under a minute.

## Prerequisites

- **Python 3.10+**
- **Container engine**: [Podman](https://podman.io/getting-started/installation) (recommended) or [Docker](https://docs.docker.com/get-docker/)

## Install

```bash
pip install pocketdock          # SDK + CLI
pip install pocketdock[agent]   # + LLM agent
```

## Build the Minimal Image

pocketdock ships Dockerfiles for six image profiles. The `minimal-python` profile (~25MB, <500ms startup) is the default:

```bash
pocketdock build minimal-python
```

Or build directly with your container engine:

```bash
# Podman
podman build -t pocketdock/minimal-python images/minimal-python/

# Docker
docker build -t pocketdock/minimal-python images/minimal-python/
```

## Run Your First Container

```python
from pocketdock import create_new_container

c = create_new_container()
result = c.run("echo hello")
print(result.stdout)   # "hello\n"
print(result.ok)       # True
c.shutdown()
```

## Context Manager

Use a context manager to automatically clean up the container:

```python
from pocketdock import create_new_container

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
# Create a container using the minimal-python profile
pocketdock create --name my-sandbox --profile minimal-python

# Run a command
pocketdock run my-sandbox echo hello

# Interactive shell
pocketdock shell my-sandbox

# Clean up
pocketdock shutdown my-sandbox --yes
```

## Next Steps

- **[Creating Containers](guide/containers.md)** — all parameters, resource limits, info, reboot
- **[Running Commands](guide/commands.md)** — blocking, streaming, and detached modes
- **[Sessions](guide/sessions.md)** — persistent shell sessions
- **[CLI Reference](cli.md)** — all 22 commands
