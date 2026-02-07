# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) deftio llc

"""AsyncContainer — the async core implementation.

All real work happens here.  The sync ``Container`` class is a thin
facade that dispatches coroutines to a background event loop.
"""

from __future__ import annotations

import contextlib
import secrets
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
