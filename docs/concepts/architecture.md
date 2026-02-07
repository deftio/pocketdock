# Architecture

pocket-dock talks directly to Podman (or Docker) over its Unix socket using raw HTTP/1.1. No external dependencies.

```
User Code / LLM Agent / CLI
        │
        ▼
  pocket-dock SDK
  ┌──────────────────────────────────────┐
  │ Container (sync) ──► AsyncContainer  │
  │   └─ _socket_client (raw HTTP/Unix) │
  └──────────────────────────────────────┘
        │  raw HTTP over Unix socket
        ▼
  Podman (rootless) / Docker Engine
```

## Key Design Rules

- **Connection-per-operation**: Each API call opens its own Unix socket connection.
- **Async core, sync facade**: `AsyncContainer` does all real work. `Container` is a sync wrapper.
- **No cached state**: Always poll live from engine.
