# Connection Model

## Connection-per-operation

Every SDK operation opens its own Unix socket connection, performs the HTTP request, and closes the connection. Unix socket connections are essentially free — no TCP handshake, no TLS negotiation.

This design means streaming, blocking, and detached operations can all run simultaneously without interfering with each other.

## Socket Auto-Detection

Detection order:

1. `POCKET_DOCK_SOCKET` environment variable
2. Podman rootless: `$XDG_RUNTIME_DIR/podman/podman.sock`
3. Podman system: `/run/podman/podman.sock`
4. Docker: `/var/run/docker.sock`
