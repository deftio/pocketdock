# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""AsyncContainer — the async core implementation.

All real work happens here.  The sync ``Container`` class is a thin
facade that dispatches coroutines to a background event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import io
import pathlib
import secrets
import tarfile
import time
from typing import TYPE_CHECKING, Any, Literal, overload

from pocketdock import _socket_client as sc
from pocketdock._callbacks import CallbackRegistry
from pocketdock._helpers import (
    build_container_info,
    build_exposed_ports,
    build_port_bindings,
    parse_mem_limit,
)
from pocketdock._logger import InstanceLogger
from pocketdock._process import AsyncExecStream, AsyncProcess
from pocketdock._session import AsyncSession
from pocketdock.errors import ContainerNotFound, ContainerNotRunning, PodmanNotRunning

if TYPE_CHECKING:
    from collections.abc import Callable

    from typing_extensions import Self

    from pocketdock.types import ContainerInfo, ExecResult

_DEFAULT_IMAGE = "pocketdock/minimal"
_DEFAULT_TIMEOUT = 30
_DEFAULT_MAX_OUTPUT = 10 * 1024 * 1024  # 10 MB


def _generate_name() -> str:
    """Generate a short random container name like ``pd-a1b2c3d4``."""
    return f"pd-{secrets.token_hex(4)}"


def _build_command(command: str, lang: str | None) -> list[str]:
    """Convert a user command string into an exec command list."""
    if lang == "python":
        return ["python3", "-c", command]
    return ["sh", "-c", command]


def _build_labels(
    name: str, *, persist: bool, project: str = "", data_path: str = ""
) -> dict[str, str]:
    """Build the standard pocketdock container labels."""
    labels = {
        "pocketdock.managed": "true",
        "pocketdock.instance": name,
        "pocketdock.persist": str(persist).lower(),
        "pocketdock.created-at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
    }
    if project:
        labels["pocketdock.project"] = project
    if data_path:
        labels["pocketdock.data-path"] = data_path
    return labels


def _build_host_config(mem_limit_bytes: int, nano_cpus: int) -> dict[str, Any] | None:
    """Build a HostConfig dict for resource limits, or None if no limits set."""
    hc: dict[str, Any] = {}
    if mem_limit_bytes > 0:
        hc["Memory"] = mem_limit_bytes
    if nano_cpus > 0:
        hc["NanoCpus"] = nano_cpus
    return hc or None


def _augment_host_config(
    host_config: dict[str, Any] | None,
    *,
    devices: list[str] | None = None,
    volumes: dict[str, str] | None = None,
    ports: dict[int, int] | None = None,
) -> dict[str, Any] | None:
    """Add devices, volumes, and port bindings to an existing host config (or create one)."""
    if devices is not None:
        if host_config is None:
            host_config = {}
        host_config["Devices"] = [
            {"PathOnHost": d, "PathInContainer": d, "CgroupPermissions": "rwm"} for d in devices
        ]
    if volumes is not None:
        if host_config is None:
            host_config = {}
        host_config["Binds"] = [f"{h}:{c}" for h, c in volumes.items()]
    if ports is not None:
        if host_config is None:
            host_config = {}
        host_config["PortBindings"] = build_port_bindings(ports)
    return host_config


class AsyncContainer:
    """Async handle to a running container.

    Created via :func:`pocketdock.async_.create_new_container`.
    Do not instantiate directly.
    """

    def __init__(  # noqa: PLR0913
        self,
        container_id: str,
        socket_path: str,
        *,
        name: str,
        image: str = "",
        timeout: int = _DEFAULT_TIMEOUT,
        mem_limit_bytes: int = 0,
        nano_cpus: int = 0,
        persist: bool = False,
        project: str = "",
        data_path: str = "",
        ports: dict[int, int] | None = None,
    ) -> None:
        self._container_id = container_id
        self._socket_path = socket_path
        self._name = name
        self._image = image
        self._timeout = timeout
        self._mem_limit_bytes = mem_limit_bytes
        self._nano_cpus = nano_cpus
        self._persist = persist
        self._project = project
        self._data_path = data_path
        self._ports = ports
        self._logger: InstanceLogger | None = None
        if data_path:
            self._logger = InstanceLogger(pathlib.Path(data_path))
        self._closed = False
        self._callbacks = CallbackRegistry()
        self._active_streams: list[AsyncExecStream] = []
        self._active_processes: list[AsyncProcess] = []
        self._active_sessions: list[AsyncSession] = []

    @property
    def container_id(self) -> str:
        """Full container ID hex string."""
        return self._container_id

    @property
    def socket_path(self) -> str:
        """Path to the container engine Unix socket."""
        return self._socket_path

    @property
    def name(self) -> str:
        """Human-readable container name (e.g. ``pd-a1b2c3d4``)."""
        return self._name

    @property
    def persist(self) -> bool:
        """Whether this container survives shutdown (stop without remove)."""
        return self._persist

    @property
    def project(self) -> str:
        """Project name this container belongs to (empty if none)."""
        return self._project

    @property
    def data_path(self) -> str:
        """Instance data directory path (empty if none)."""
        return self._data_path

    @overload
    async def run(
        self,
        command: str,
        *,
        stream: Literal[True],
        timeout: float | None = ...,
        max_output: int = ...,
        lang: str | None = ...,
    ) -> AsyncExecStream: ...

    @overload
    async def run(
        self,
        command: str,
        *,
        detach: Literal[True],
        timeout: float | None = ...,
        max_output: int = ...,
        lang: str | None = ...,
    ) -> AsyncProcess: ...

    @overload
    async def run(
        self,
        command: str,
        *,
        timeout: float | None = ...,
        max_output: int = ...,
        lang: str | None = ...,
    ) -> ExecResult: ...

    @overload
    async def run(
        self,
        command: str,
        *,
        stream: bool,
        detach: bool,
        timeout: float | None = ...,
        max_output: int = ...,
        lang: str | None = ...,
    ) -> ExecResult | AsyncExecStream | AsyncProcess: ...

    async def run(  # noqa: PLR0913
        self,
        command: str,
        *,
        stream: bool = False,
        detach: bool = False,
        timeout: float | None = None,
        max_output: int = _DEFAULT_MAX_OUTPUT,
        lang: str | None = None,
    ) -> ExecResult | AsyncExecStream | AsyncProcess:
        """Execute a command inside the container.

        Args:
            command: The command string to execute.
            stream: If ``True``, return an async iterator of ``StreamChunk``.
            detach: If ``True``, return a ``Process`` handle.
            timeout: Max seconds to wait. ``None`` uses the container default.
            max_output: Maximum bytes to accumulate before truncating.
            lang: Language shorthand (e.g. ``"python"``). Default runs via
                ``sh -c``.

        Returns:
            ``ExecResult``, ``AsyncExecStream``, or ``AsyncProcess``.

        """
        if stream and detach:
            msg = "stream and detach are mutually exclusive"
            raise ValueError(msg)

        cmd = _build_command(command, lang)

        if stream:
            exec_id = await sc._exec_create(  # noqa: SLF001
                self._socket_path, self._container_id, cmd
            )
            gen, writer = await sc._exec_start_stream(  # noqa: SLF001
                self._socket_path, exec_id
            )
            obj = AsyncExecStream(exec_id, gen, writer, self._socket_path, time.monotonic())
            self._active_streams.append(obj)
            return obj

        if detach:
            exec_id = await sc._exec_create(  # noqa: SLF001
                self._socket_path, self._container_id, cmd
            )
            gen, writer = await sc._exec_start_stream(  # noqa: SLF001
                self._socket_path, exec_id
            )
            detach_log = None
            if self._logger is not None:
                detach_log = self._logger.start_detach_log(command)
            proc = AsyncProcess(exec_id, self, gen, writer, self._callbacks, log_handle=detach_log)
            self._active_processes.append(proc)
            return proc

        t = timeout if timeout is not None else self._timeout
        started_at = datetime.datetime.now(tz=datetime.timezone.utc)
        result = await sc.exec_command(
            self._socket_path,
            self._container_id,
            cmd,
            max_output=max_output,
            timeout=t,
        )
        if self._logger is not None:
            self._logger.log_run(command, result, started_at)
        return result

    async def info(self) -> ContainerInfo:
        """Return a live snapshot of the container's state and resource usage.

        Makes 1-3 API calls depending on the container state: inspect always,
        stats and top only when running.
        """
        inspect_data = await sc.inspect_container(self._socket_path, self._container_id)
        stats_data: dict[str, object] | None = None
        top_data: dict[str, object] | None = None

        state = inspect_data.get("State", {})
        if isinstance(state, dict) and state.get("Running"):
            with contextlib.suppress(ContainerNotRunning, ContainerNotFound):
                stats_data, top_data = await asyncio.gather(
                    sc.get_container_stats(self._socket_path, self._container_id),
                    sc.get_container_top(self._socket_path, self._container_id),
                )

        return build_container_info(inspect_data, stats_data, top_data, self._name)

    async def reboot(self, *, fresh: bool = False) -> None:
        """Restart the container.

        Args:
            fresh: If ``False`` (default), restart in place — preserves the
                filesystem but kills all processes.  If ``True``, remove the
                container and create a new one with the same image and config.

        """
        if not fresh:
            await sc.restart_container(self._socket_path, self._container_id)
            return

        # Fresh reboot: remove old container, create new one
        with contextlib.suppress(ContainerNotRunning, ContainerNotFound):
            await sc.stop_container(self._socket_path, self._container_id)
        with contextlib.suppress(ContainerNotFound):
            await sc.remove_container(self._socket_path, self._container_id, force=True)

        labels = _build_labels(
            self._name, persist=self._persist, project=self._project, data_path=self._data_path
        )
        host_config = _build_host_config(self._mem_limit_bytes, self._nano_cpus)
        host_config = _augment_host_config(host_config, ports=self._ports)
        exposed_ports = build_exposed_ports(self._ports) if self._ports else None
        self._container_id = await sc.create_container(
            self._socket_path,
            self._image or _DEFAULT_IMAGE,
            command=["sleep", "infinity"],
            labels=labels,
            host_config=host_config,
            exposed_ports=exposed_ports,
        )
        await sc.start_container(self._socket_path, self._container_id)

    async def write_file(self, path: str, content: str | bytes) -> None:
        """Write a file into the container.

        Creates parent directories as needed.

        Args:
            path: Absolute path inside the container.
            content: File contents (str is encoded as UTF-8).

        """
        data = content.encode("utf-8") if isinstance(content, str) else content
        dest_dir = str(pathlib.PurePosixPath(path).parent)
        file_name = pathlib.PurePosixPath(path).name

        # Ensure parent directory exists (Docker archive API returns 404 otherwise)
        await self.run(f"mkdir -p {dest_dir}")

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name=file_name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        await sc.push_archive(self._socket_path, self._container_id, dest_dir, buf.getvalue())

    async def read_file(self, path: str) -> bytes:
        """Read a file from the container.

        Args:
            path: Absolute path inside the container.

        Returns:
            The file contents as bytes.

        """
        tar_data = await sc.pull_archive(self._socket_path, self._container_id, path)
        buf = io.BytesIO(tar_data)
        with tarfile.open(fileobj=buf, mode="r") as tar:
            for member in tar.getmembers():
                if member.isfile():
                    extracted = tar.extractfile(member)
                    if extracted is not None:
                        return extracted.read()
        msg = f"no file found in archive for {path}"
        raise FileNotFoundError(msg)

    async def list_files(self, path: str = "/home/sandbox") -> list[str]:
        """List directory contents inside the container.

        Args:
            path: Directory path inside the container.

        Returns:
            List of filenames (not full paths).

        """
        result = await self.run(f"ls -1a {path}")
        if not result.ok:
            msg = f"ls failed: {result.stderr.strip()}"
            raise FileNotFoundError(msg)
        return [f for f in result.stdout.strip().split("\n") if f and f not in (".", "..")]

    async def push(self, src: str, dest: str) -> None:
        """Copy a file or directory from the host into the container.

        Args:
            src: Path on the host filesystem.
            dest: Destination path inside the container.

        """
        host_path = pathlib.Path(src)
        if not host_path.exists():  # noqa: ASYNC240
            msg = f"source path does not exist: {src}"
            raise FileNotFoundError(msg)

        def _reset_tar_info(info: tarfile.TarInfo) -> tarfile.TarInfo:
            """Reset ownership and permissions for container compatibility."""
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            if info.isdir():
                info.mode = 0o755
            else:
                info.mode = 0o644
            return info

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            if host_path.is_dir():  # noqa: ASYNC240
                dest_name = pathlib.PurePosixPath(dest).name
                tar.add(str(host_path), arcname=dest_name, filter=_reset_tar_info)
            else:
                tar.add(
                    str(host_path),
                    arcname=pathlib.PurePosixPath(dest).name,
                    filter=_reset_tar_info,
                )

        dest_dir = str(pathlib.PurePosixPath(dest).parent)
        await sc.push_archive(self._socket_path, self._container_id, dest_dir, buf.getvalue())

    async def pull(self, src: str, dest: str) -> None:
        """Copy a file or directory from the container to the host.

        Args:
            src: Path inside the container.
            dest: Destination path on the host filesystem.

        """
        tar_data = await sc.pull_archive(self._socket_path, self._container_id, src)
        dest_path = pathlib.Path(dest)
        buf = io.BytesIO(tar_data)
        with tarfile.open(fileobj=buf, mode="r") as tar:
            members = tar.getmembers()
            if len(members) == 1 and members[0].isfile():
                extracted = tar.extractfile(members[0])
                if extracted is not None:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    dest_path.write_bytes(extracted.read())  # noqa: ASYNC240
                    return
            # Directory or multiple files: extract all
            dest_path.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240
            tar.extractall(dest_path, filter="data")

    def on_stdout(self, fn: Callable[..., object]) -> None:
        """Register a callback for stdout data from detached processes."""
        self._callbacks.on_stdout(fn)

    def on_stderr(self, fn: Callable[..., object]) -> None:
        """Register a callback for stderr data from detached processes."""
        self._callbacks.on_stderr(fn)

    def on_exit(self, fn: Callable[..., object]) -> None:
        """Register a callback for process exit from detached processes."""
        self._callbacks.on_exit(fn)

    async def session(self) -> AsyncSession:
        """Open a persistent shell session inside the container.

        Returns an :class:`AsyncSession` connected to a bash process.
        Commands sent through the session share state (cwd, env vars).
        """
        exec_id = await sc._exec_create(  # noqa: SLF001
            self._socket_path, self._container_id, ["bash"], attach_stdin=True
        )
        gen, writer = await sc._exec_start_stream(  # noqa: SLF001
            self._socket_path, exec_id
        )
        log_handle = None
        if self._logger is not None:
            log_handle = self._logger.start_session_log(exec_id)
        sess = AsyncSession(
            exec_id, gen, writer, self._socket_path, self._container_id, log_handle=log_handle
        )
        self._active_sessions.append(sess)
        return sess

    async def snapshot(self, image_name: str) -> str:
        """Commit the container's current filesystem as a new image.

        Args:
            image_name: Image name, optionally with tag (e.g. ``"my-image:v1"``).
                If no tag is provided, defaults to ``"latest"``.

        Returns:
            The new image ID.

        """
        if ":" in image_name:
            repo, tag = image_name.rsplit(":", 1)
        else:
            repo = image_name
            tag = "latest"
        return await sc.commit_container(self._socket_path, self._container_id, repo, tag)

    async def shutdown(self, *, force: bool = False) -> None:
        """Stop and remove the container.

        Args:
            force: If ``True``, kill the container immediately (``SIGKILL``).

        """
        if self._closed:
            return
        self._closed = True

        # Clean up active sessions
        for sess in self._active_sessions:
            await sess._close()  # noqa: SLF001
        self._active_sessions.clear()

        # Clean up active streams
        for s in self._active_streams:
            await s._close()  # noqa: SLF001
        self._active_streams.clear()

        # Clean up active processes
        for p in self._active_processes:
            await p._cancel()  # noqa: SLF001
        self._active_processes.clear()

        if self._persist:
            with contextlib.suppress(ContainerNotRunning, ContainerNotFound):
                await sc.stop_container(self._socket_path, self._container_id)
        elif force:
            await sc.remove_container(self._socket_path, self._container_id, force=True)
        else:
            with contextlib.suppress(ContainerNotRunning, ContainerNotFound):
                await sc.stop_container(self._socket_path, self._container_id)
            with contextlib.suppress(ContainerNotFound):
                await sc.remove_container(self._socket_path, self._container_id, force=True)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.shutdown()


async def create_new_container(  # noqa: PLR0913
    *,
    image: str = _DEFAULT_IMAGE,
    name: str | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
    mem_limit: str | None = None,
    cpu_percent: int | None = None,
    persist: bool = False,
    volumes: dict[str, str] | None = None,
    project: str | None = None,
    profile: str | None = None,
    devices: list[str] | None = None,
    ports: dict[int, int] | None = None,
) -> AsyncContainer:
    """Create and start a new container, returning an async handle.

    Args:
        image: Container image to use.
        name: Container name. Auto-generated if ``None``.
        timeout: Default exec timeout in seconds.
        mem_limit: Memory limit (e.g. ``"256m"``, ``"1g"``).
        cpu_percent: CPU usage cap as a percentage (e.g. ``50`` for 50%).
        persist: If ``True``, shutdown stops but does not remove the container.
        volumes: Host-to-container mount mappings (e.g. ``{"/host": "/container"}``).
        project: Project name. Auto-detected from ``.pocketdock/`` if ``None``.
        profile: Image profile name (e.g. ``"dev"``, ``"agent"``). Resolved to
            an image tag via :func:`pocketdock.profiles.resolve_profile`. Ignored
            when *image* is explicitly set to a non-default value.
        devices: Host device paths to passthrough (e.g. ``["/dev/ttyUSB0"]``).
        ports: Host-to-container port mappings (e.g. ``{8080: 80}``).

    Returns:
        A running :class:`AsyncContainer`.

    """
    from pocketdock.projects import (  # noqa: PLC0415
        ensure_instance_dir,
        find_project_root,
        get_project_name,
        write_instance_metadata,
    )

    if name is None:
        name = _generate_name()

    # Resolve profile → image tag when image was not explicitly overridden
    if profile is not None and image == _DEFAULT_IMAGE:
        from pocketdock.profiles import resolve_profile  # noqa: PLC0415

        profile_info = resolve_profile(profile)
        image = profile_info.image_tag

    socket_path = sc.detect_socket()
    if socket_path is None:
        raise PodmanNotRunning

    mem_limit_bytes = parse_mem_limit(mem_limit) if mem_limit is not None else 0
    nano_cpus = cpu_percent * 10_000_000 if cpu_percent is not None else 0

    # Resolve project + instance directory for persistent containers
    resolved_project = project or ""
    data_path = ""
    if persist:
        project_root = find_project_root()
        if project_root is not None:
            if not resolved_project:
                resolved_project = get_project_name(project_root)
            instance_dir = ensure_instance_dir(project_root, name)
            data_path = str(instance_dir)
            write_instance_metadata(
                instance_dir,
                container_id="(pending)",
                name=name,
                image=image,
                project=resolved_project,
                created_at=datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
                persist=True,
                mem_limit=mem_limit or "",
                cpu_percent=cpu_percent or 0,
                ports=ports,
            )

    labels = _build_labels(name, persist=persist, project=resolved_project, data_path=data_path)
    host_config = _build_host_config(mem_limit_bytes, nano_cpus)
    host_config = _augment_host_config(host_config, devices=devices, volumes=volumes, ports=ports)
    exposed_ports = build_exposed_ports(ports) if ports else None

    container_id = await sc.create_container(
        socket_path,
        image,
        command=["sleep", "infinity"],
        labels=labels,
        host_config=host_config,
        exposed_ports=exposed_ports,
    )
    await sc.start_container(socket_path, container_id)

    # Update instance metadata with real container ID
    if data_path:
        write_instance_metadata(
            pathlib.Path(data_path),
            container_id=container_id,
            name=name,
            image=image,
            project=resolved_project,
            created_at=datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
            persist=True,
            mem_limit=mem_limit or "",
            cpu_percent=cpu_percent or 0,
            ports=ports,
        )

    return AsyncContainer(
        container_id,
        socket_path,
        name=name,
        image=image,
        timeout=timeout,
        mem_limit_bytes=mem_limit_bytes,
        nano_cpus=nano_cpus,
        persist=persist,
        project=resolved_project,
        data_path=data_path,
        ports=ports,
    )
