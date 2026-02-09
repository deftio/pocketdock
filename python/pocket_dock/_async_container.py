# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""AsyncContainer — the async core implementation.

All real work happens here.  The sync ``Container`` class is a thin
facade that dispatches coroutines to a background event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import pathlib
import secrets
import tarfile
import time
from typing import TYPE_CHECKING, Any, Literal, overload

from pocket_dock import _socket_client as sc
from pocket_dock._callbacks import CallbackRegistry
from pocket_dock._helpers import build_container_info, parse_mem_limit
from pocket_dock._process import AsyncExecStream, AsyncProcess
from pocket_dock.errors import ContainerNotFound, ContainerNotRunning, PodmanNotRunning

if TYPE_CHECKING:
    from collections.abc import Callable

    from typing_extensions import Self

    from pocket_dock.types import ContainerInfo, ExecResult

_DEFAULT_IMAGE = "pocket-dock/minimal"
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


def _build_host_config(mem_limit_bytes: int, nano_cpus: int) -> dict[str, Any] | None:
    """Build a HostConfig dict for resource limits, or None if no limits set."""
    hc: dict[str, Any] = {}
    if mem_limit_bytes > 0:
        hc["Memory"] = mem_limit_bytes
    if nano_cpus > 0:
        hc["NanoCpus"] = nano_cpus
    return hc or None


class AsyncContainer:
    """Async handle to a running container.

    Created via :func:`pocket_dock.async_.create_new_container`.
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
    ) -> None:
        self._container_id = container_id
        self._socket_path = socket_path
        self._name = name
        self._image = image
        self._timeout = timeout
        self._mem_limit_bytes = mem_limit_bytes
        self._nano_cpus = nano_cpus
        self._closed = False
        self._callbacks = CallbackRegistry()
        self._active_streams: list[AsyncExecStream] = []
        self._active_processes: list[AsyncProcess] = []

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
            proc = AsyncProcess(exec_id, self, gen, writer, self._callbacks)
            self._active_processes.append(proc)
            return proc

        t = timeout if timeout is not None else self._timeout
        return await sc.exec_command(
            self._socket_path,
            self._container_id,
            cmd,
            max_output=max_output,
            timeout=t,
        )

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

        labels = {
            "pocket-dock.managed": "true",
            "pocket-dock.instance": self._name,
        }
        host_config = _build_host_config(self._mem_limit_bytes, self._nano_cpus)
        self._container_id = await sc.create_container(
            self._socket_path,
            self._image or _DEFAULT_IMAGE,
            command=["sleep", "infinity"],
            labels=labels,
            host_config=host_config,
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

    async def shutdown(self, *, force: bool = False) -> None:
        """Stop and remove the container.

        Args:
            force: If ``True``, kill the container immediately (``SIGKILL``).

        """
        if self._closed:
            return
        self._closed = True

        # Clean up active streams
        for s in self._active_streams:
            await s._close()  # noqa: SLF001
        self._active_streams.clear()

        # Clean up active processes
        for p in self._active_processes:
            await p._cancel()  # noqa: SLF001
        self._active_processes.clear()

        if force:
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


async def create_new_container(
    *,
    image: str = _DEFAULT_IMAGE,
    name: str | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
    mem_limit: str | None = None,
    cpu_percent: int | None = None,
) -> AsyncContainer:
    """Create and start a new container, returning an async handle.

    Args:
        image: Container image to use.
        name: Container name. Auto-generated if ``None``.
        timeout: Default exec timeout in seconds.
        mem_limit: Memory limit (e.g. ``"256m"``, ``"1g"``).
        cpu_percent: CPU usage cap as a percentage (e.g. ``50`` for 50%).

    Returns:
        A running :class:`AsyncContainer`.

    """
    if name is None:
        name = _generate_name()

    socket_path = sc.detect_socket()
    if socket_path is None:
        raise PodmanNotRunning

    mem_limit_bytes = parse_mem_limit(mem_limit) if mem_limit is not None else 0
    nano_cpus = cpu_percent * 10_000_000 if cpu_percent is not None else 0

    labels = {
        "pocket-dock.managed": "true",
        "pocket-dock.instance": name,
    }
    host_config = _build_host_config(mem_limit_bytes, nano_cpus)

    container_id = await sc.create_container(
        socket_path,
        image,
        command=["sleep", "infinity"],
        labels=labels,
        host_config=host_config,
    )
    await sc.start_container(socket_path, container_id)

    return AsyncContainer(
        container_id,
        socket_path,
        name=name,
        image=image,
        timeout=timeout,
        mem_limit_bytes=mem_limit_bytes,
        nano_cpus=nano_cpus,
    )
