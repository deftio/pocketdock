# Quickstart

## Prerequisites

- Python 3.10+
- [Podman](https://podman.io/getting-started/installation) (recommended) or Docker

## Install

```bash
pip install pocket-dock
```

## Build the minimal image

```bash
podman build -t pocket-dock/minimal images/minimal/
```

## Run your first container

```python
from pocket_dock import create_new_container

c = create_new_container()
result = c.run("echo hello")
print(result.stdout)  # "hello\n"
c.shutdown()
```
