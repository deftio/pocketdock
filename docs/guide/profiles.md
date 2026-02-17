# Image Profiles

pocketdock ships six pre-baked Dockerfiles for common use cases.

## Available Profiles

| Profile | Size | Base | Contents | Default Network |
|---------|------|------|----------|-----------------|
| **minimal-python** | ~25 MB | Alpine 3.21 | Python 3, pip, bash | Disabled |
| **minimal-node** | ~60 MB | node:22-alpine | Node.js 22, npm, bash | Disabled |
| **minimal-bun** | ~100 MB | oven/bun:1-alpine | Bun runtime, bash | Disabled |
| **dev** | ~250 MB | python:3.12-slim | Git, curl, jq, vim, build tools, ipython | Enabled |
| **agent** | ~350 MB | python:3.12-slim | requests, pandas, numpy, beautifulsoup4, pillow | Disabled |
| **embedded** | ~450 MB | Alpine 3.21 | GCC, CMake, ARM cross-compiler, Arduino CLI, PlatformIO | Enabled |

## Using Profiles

### With the `profile` Parameter

```python
from pocketdock import create_new_container

with create_new_container(profile="dev") as c:
    result = c.run("python --version")
    print(result.stdout)
```

The `profile` parameter resolves to the profile's image tag (e.g., `pocketdock/dev`) and applies the profile's default network setting.

### With the `image` Parameter

You can also specify the image tag directly:

```python
with create_new_container(image="pocketdock/agent") as c:
    result = c.run("python -c 'import pandas; print(pandas.__version__)'", lang=None)
```

## Building Profiles

### Via CLI

```bash
# Build all profiles
pocketdock build

# Build a specific profile
pocketdock build minimal-python
pocketdock build dev
```

### Via Container Engine

```bash
docker build -t pocketdock/minimal-python images/minimal-python/
docker build -t pocketdock/dev images/dev/
docker build -t pocketdock/agent images/agent/
docker build -t pocketdock/embedded images/embedded/
```

## Listing Profiles

### SDK

```python
from pocketdock import list_profiles, resolve_profile

# List all profiles
profiles = list_profiles()
for p in profiles:
    print(f"{p.name}: {p.description} ({p.size_estimate})")

# Resolve a single profile
info = resolve_profile("dev")
info.name            # "dev"
info.image_tag       # "pocketdock/dev"
info.network_default # True
info.description     # "Development tools, git, curl, ..."
info.size_estimate   # "~250 MB"
info.dockerfile_dir  # path to Dockerfile directory
```

### CLI

```bash
pocketdock profiles
pocketdock profiles --json
```

## Export and Import

Transfer images between machines for air-gapped environments:

```bash
# Export all profile images to a tar.gz file
pocketdock export --all -o images.tar.gz

# Import on another machine
pocketdock import images.tar.gz
```

## Device Passthrough

For the `embedded` profile (or any container), pass host devices into the container:

```python
with create_new_container(profile="embedded", devices=["/dev/ttyUSB0"]) as c:
    result = c.run("ls /dev/ttyUSB0")
```

The `devices` parameter accepts a list of host device paths.

## ProfileInfo

Each profile is represented as a `ProfileInfo` dataclass:

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Profile name (e.g., `"minimal-python"`) |
| `image_tag` | `str` | Docker/Podman image tag |
| `dockerfile_dir` | `str` | Path to the Dockerfile directory |
| `network_default` | `bool` | Whether networking is enabled by default |
| `description` | `str` | Human-readable description |
| `size_estimate` | `str` | Approximate image size |
