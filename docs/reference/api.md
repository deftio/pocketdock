# API Reference

## Socket Client (Low-Level)

The socket client provides low-level async functions for communicating with the container engine.

### `detect_socket() -> str | None`

Auto-detect an available container engine socket.

### `ping(socket_path: str) -> str`

Ping the container engine. Returns `"OK"` on success.

### `create_container(socket_path, image, ...) -> str`

Create a container. Returns the container ID.

### `start_container(socket_path, container_id) -> None`

Start a stopped container.

### `stop_container(socket_path, container_id, timeout) -> None`

Stop a running container.

### `remove_container(socket_path, container_id, force) -> None`

Remove a container.

### `exec_command(socket_path, container_id, command, ...) -> ExecResult`

Execute a command inside a running container.
