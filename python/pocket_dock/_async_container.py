# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""AsyncContainer — the async core implementation.

All real work happens here.  The sync ``Container`` class is a thin
facade that dispatches coroutines to a background event loop.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import secrets
import tarfile
from typing import TYPE_CHECKING

from pocket_dock import _socket_client as sc
from pocket_dock.errors import ContainerNotFound, ContainerNotRunning, PodmanNotRunning

if TYPE_CHECKING:
    from typing_extensions import Self

    from pocket_dock.types import ExecResult

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


class AsyncContainer:
    """Async handle to a running container.

    Created via :func:`pocket_dock.async_.create_new_container`.
    Do not instantiate directly.
    """

    def __init__(
        self,
        container_id: str,
        socket_path: str,
        *,
        name: str,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        self._container_id = container_id
        self._socket_path = socket_path
        self._name = name
        self._timeout = timeout
        self._closed = False

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

    async def run(
        self,
        command: str,
        *,
        timeout: float | None = None,
        max_output: int = _DEFAULT_MAX_OUTPUT,
        lang: str | None = None,
    ) -> ExecResult:
        """Execute a command inside the container and return the result.

        Args:
            command: The command string to execute.
            timeout: Max seconds to wait. ``None`` uses the container default.
            max_output: Maximum bytes to accumulate before truncating.
            lang: Language shorthand (e.g. ``"python"``). Default runs via
                ``sh -c``.

        Returns:
            An :class:`~pocket_dock.types.ExecResult`.

        """
        t = timeout if timeout is not None else self._timeout
        cmd = _build_command(command, lang)
        return await sc.exec_command(
            self._socket_path,
            self._container_id,
            cmd,
            max_output=max_output,
            timeout=t,
        )

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

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            if host_path.is_dir():  # noqa: ASYNC240
                dest_name = pathlib.PurePosixPath(dest).name
                tar.add(str(host_path), arcname=dest_name)
            else:
                tar.add(str(host_path), arcname=pathlib.PurePosixPath(dest).name)

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

    async def shutdown(self, *, force: bool = False) -> None:
        """Stop and remove the container.

        Args:
            force: If ``True``, kill the container immediately (``SIGKILL``).

        """
        if self._closed:
            return
        self._closed = True
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
) -> AsyncContainer:
    """Create and start a new container, returning an async handle.

    Args:
        image: Container image to use.
        name: Container name. Auto-generated if ``None``.
        timeout: Default exec timeout in seconds.

    Returns:
        A running :class:`AsyncContainer`.

    """
    if name is None:
        name = _generate_name()

    socket_path = sc.detect_socket()
    if socket_path is None:
        raise PodmanNotRunning

    labels = {
        "pocket-dock.managed": "true",
        "pocket-dock.instance": name,
    }

    container_id = await sc.create_container(
        socket_path,
        image,
        command=["sleep", "infinity"],
        labels=labels,
    )
    await sc.start_container(socket_path, container_id)

    return AsyncContainer(
        container_id,
        socket_path,
        name=name,
        timeout=timeout,
    )
