# Error Reference

## Hierarchy

```
PocketDockError
├── SocketError
│   ├── SocketConnectionError
│   ├── SocketCommunicationError
│   └── PodmanNotRunning
├── ContainerError
│   ├── ContainerNotFound
│   ├── ContainerNotRunning
│   └── ContainerGone
└── ImageNotFound
```

## `PocketDockError`

Base exception for all pocket-dock errors.

## Socket Errors

- **`SocketConnectionError`** — Cannot connect to the container engine socket.
- **`SocketCommunicationError`** — Error during communication over the socket.
- **`PodmanNotRunning`** — No container engine socket found.

## Container Errors

- **`ContainerNotFound`** — Container does not exist (404).
- **`ContainerNotRunning`** — Container exists but is not running (409).
- **`ContainerGone`** — Container was removed externally.

## Image Errors

- **`ImageNotFound`** — Requested image does not exist locally.
