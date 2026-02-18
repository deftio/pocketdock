# pocketdock demo

This directory is bundled inside the `minimal-python` container image.

## Contents

- `index.html` — a simple landing page confirming you are inside a container
- `serve.py` — a stdlib web server that serves this directory on port 8000

## Usage

```bash
# Create a container with port mapping
pocketdock create --name my-web --profile minimal-python -p 8080:8000

# Open a shell and start the server
pocketdock shell my-web
cd demo && python serve.py

# Then open http://localhost:8080 in your browser
```

Port mapping (`-p 8080:8000`) must be set at container creation time.

Full docs: https://deftio.github.io/pocketdock/
