# Image Profiles

pocket-dock ships four pre-baked Dockerfiles for common use cases.

## Available Profiles

| Profile | Size | Base | Contents | Default Network |
|---------|------|------|----------|-----------------|
| **minimal** | ~25 MB | Alpine 3.21 | Python 3, pip, bash | Disabled |
| **dev** | ~250 MB | python:3.12-slim | Git, curl, jq, vim, build tools, ipython | Enabled |
| **agent** | ~350 MB | python:3.12-slim | requests, pandas, numpy, beautifulsoup4, pillow | Disabled |
| **embedded** | ~450 MB | Alpine 3.21 | GCC, CMake, ARM cross-compiler, Arduino CLI, PlatformIO | Enabled |

## Using Profiles

### With the `profile` Parameter

```python
from pocket_dock import create_new_container

with create_new_container(profile="dev") as c:
    result = c.run("python --version")
    print(result.stdout)
```

The `profile` parameter resolves to the profile's image tag (e.g., `pocket-dock/dev`) and applies the profile's default network setting.

### With the `image` Parameter

You can also specify the image tag directly:

```python
with create_new_container(image="pocket-dock/agent") as c:
    result = c.run("python -c 'import pandas; print(pandas.__version__)'", lang=None)
```

## Building Profiles

### Via CLI

```bash
# Build all profiles
pocket-dock build

# Build a specific profile
pocket-dock build minimal
pocket-dock build dev
```

### Via Container Engine

```bash
docker build -t pocket-dock/minimal images/minimal/
docker build -t pocket-dock/dev images/dev/
docker build -t pocket-dock/agent images/agent/
docker build -t pocket-dock/embedded images/embedded/
```

## Listing Profiles

### SDK

```python
from pocket_dock import list_profiles, resolve_profile

# List all profiles
profiles = list_profiles()
for p in profiles:
    print(f"{p.name}: {p.description} ({p.size_estimate})")

# Resolve a single profile
info = resolve_profile("dev")
info.name            # "dev"
info.image_tag       # "pocket-dock/dev"
info.network_default # True
info.description     # "Development tools, git, curl, ..."
info.size_estimate   # "~250 MB"
info.dockerfile_dir  # path to Dockerfile directory
```

### CLI

```bash
pocket-dock profiles
pocket-dock profiles --json
```

## Export and Import

Transfer images between machines for air-gapped environments:

```bash
# Export all profile images to a tar.gz file
pocket-dock export --all -o images.tar.gz

# Import on another machine
pocket-dock import images.tar.gz
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
| `name` | `str` | Profile name (e.g., `"minimal"`) |
| `image_tag` | `str` | Docker/Podman image tag |
| `dockerfile_dir` | `str` | Path to the Dockerfile directory |
| `network_default` | `bool` | Whether networking is enabled by default |
| `description` | `str` | Human-readable description |
| `size_estimate` | `str` | Approximate image size |
