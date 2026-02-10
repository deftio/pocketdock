"""Unit tests for AsyncSession, SyncSession, and session integration.

These tests do NOT require a running container engine.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pocket_dock._session import _SENTINEL_RE, AsyncSession, _PendingCommand
from pocket_dock._stream import STREAM_STDERR, STREAM_STDOUT
from pocket_dock._sync_container import Container, SyncSession, _LoopThread
from pocket_dock.errors import SessionClosed
from pocket_dock.types import ExecResult

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


# --- Sentinel regex ---


def test_sentinel_regex_matches_valid() -> None:
    match = _SENTINEL_RE.search("__PD_abcdef0123456789_0__")
    assert match is not None
    assert match.group(1) == "abcdef0123456789"
    assert match.group(2) == "0"


def test_sentinel_regex_matches_nonzero_exit() -> None:
    match = _SENTINEL_RE.search("__PD_1234567890abcdef_127__")
    assert match is not None
    assert match.group(2) == "127"


def test_sentinel_regex_no_match_short_uuid() -> None:
    match = _SENTINEL_RE.search("__PD_abc_0__")
    assert match is None


def test_sentinel_regex_no_match_no_exit_code() -> None:
    match = _SENTINEL_RE.search("__PD_abcdef0123456789___")
    assert match is None


def test_sentinel_regex_embedded_in_line() -> None:
    match = _SENTINEL_RE.search("some prefix __PD_abcdef0123456789_42__ suffix")
    assert match is not None
    assert match.group(2) == "42"


# --- _PendingCommand ---


def test_pending_command_defaults() -> None:
    event = asyncio.Event()
    pc = _PendingCommand("uuid1234567890ab", event, time.monotonic())
    assert pc.uuid == "uuid1234567890ab"
    assert pc.stdout == []
    assert pc.stderr == []
    assert pc.exit_code == -1


# --- Helpers ---


async def _gen_from_list(
    items: list[tuple[int, bytes]],
) -> AsyncGenerator[tuple[int, bytes], None]:
    for item in items:
        yield item


def _mock_writer() -> MagicMock:
    writer = MagicMock()
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    return writer


async def _delayed_gen(
    items: list[tuple[int, bytes]],
    gate: asyncio.Event,
) -> AsyncGenerator[tuple[int, bytes], None]:
    """Yield items only after *gate* is set (so pending command can be registered first)."""
    await gate.wait()
    for item in items:
        yield item


def _make_session(
    frames: list[tuple[int, bytes]] | None = None,
    writer: MagicMock | None = None,
) -> AsyncSession:
    if frames is None:
        frames = []
    if writer is None:
        writer = _mock_writer()
    return AsyncSession(
        "eid",
        _gen_from_list(frames),
        writer,
        "/tmp/s.sock",
        "cid",
    )


# --- AsyncSession.send ---


async def test_send_writes_to_stdin() -> None:
    writer = _mock_writer()
    sess = _make_session(writer=writer)
    await sess.send("echo hello")
    writer.write.assert_called_with(b"echo hello\n")
    writer.drain.assert_awaited()
    await sess.close()


async def test_send_raises_when_closed() -> None:
    sess = _make_session()
    await sess.close()
    with pytest.raises(SessionClosed):
        await sess.send("echo x")


# --- AsyncSession.send_and_wait ---


async def test_send_and_wait_basic() -> None:
    uuid_hex = "a" * 16
    sentinel_line = f"__PD_{uuid_hex}_0__"
    gate = asyncio.Event()
    frames = [
        (STREAM_STDOUT, b"hello world\n"),
        (STREAM_STDOUT, f"{sentinel_line}\n".encode()),
    ]
    writer = _mock_writer()
    sess = AsyncSession("eid", _delayed_gen(frames, gate), writer, "/tmp/s.sock", "cid")

    with patch("pocket_dock._session.uuid.uuid4") as mock_uuid:
        mock_uuid.return_value = MagicMock(hex=uuid_hex + "extrastuff")
        task = asyncio.ensure_future(sess.send_and_wait("echo hello world"))
        await asyncio.sleep(0.01)
        gate.set()
        result = await task

    assert isinstance(result, ExecResult)
    assert result.exit_code == 0
    assert "hello world\n" in result.stdout
    assert result.duration_ms > 0
    await sess.close()


async def test_send_and_wait_nonzero_exit() -> None:
    uuid_hex = "b" * 16
    sentinel_line = f"__PD_{uuid_hex}_1__"
    gate = asyncio.Event()
    frames = [
        (STREAM_STDOUT, f"{sentinel_line}\n".encode()),
    ]
    writer = _mock_writer()
    sess = AsyncSession("eid", _delayed_gen(frames, gate), writer, "/tmp/s.sock", "cid")

    with patch("pocket_dock._session.uuid.uuid4") as mock_uuid:
        mock_uuid.return_value = MagicMock(hex=uuid_hex + "extrastuff")
        task = asyncio.ensure_future(sess.send_and_wait("false"))
        await asyncio.sleep(0.01)
        gate.set()
        result = await task

    assert result.exit_code == 1
    assert result.ok is False
    await sess.close()


async def test_send_and_wait_captures_stderr() -> None:
    uuid_hex = "c" * 16
    sentinel_line = f"__PD_{uuid_hex}_0__"
    gate = asyncio.Event()
    frames = [
        (STREAM_STDERR, b"error output"),
        (STREAM_STDOUT, f"{sentinel_line}\n".encode()),
    ]
    writer = _mock_writer()
    sess = AsyncSession("eid", _delayed_gen(frames, gate), writer, "/tmp/s.sock", "cid")

    with patch("pocket_dock._session.uuid.uuid4") as mock_uuid:
        mock_uuid.return_value = MagicMock(hex=uuid_hex + "extrastuff")
        task = asyncio.ensure_future(sess.send_and_wait("echo err >&2"))
        await asyncio.sleep(0.01)
        gate.set()
        result = await task

    assert result.stderr == "error output"
    await sess.close()


async def test_send_and_wait_timeout() -> None:
    async def _slow_gen() -> AsyncGenerator[tuple[int, bytes], None]:
        yield (STREAM_STDOUT, b"partial output\n")
        await asyncio.sleep(10)  # keep alive so timeout fires, not EOF

    writer = _mock_writer()
    sess = AsyncSession("eid", _slow_gen(), writer, "/tmp/s.sock", "cid")

    result = await sess.send_and_wait("sleep 100", timeout=0.1)

    assert result.timed_out is True
    assert result.exit_code == -1
    assert "partial output\n" in result.stdout
    await sess.close()


async def test_send_and_wait_double_pending_raises() -> None:
    uuid_hex = "d" * 16

    async def _slow_gen() -> AsyncGenerator[tuple[int, bytes], None]:
        await asyncio.sleep(10)
        yield (STREAM_STDOUT, b"never")

    writer = _mock_writer()
    sess = AsyncSession("eid", _slow_gen(), writer, "/tmp/s.sock", "cid")

    with patch("pocket_dock._session.uuid.uuid4") as mock_uuid:
        mock_uuid.return_value = MagicMock(hex=uuid_hex + "extrastuff")

        # Start first send_and_wait (will timeout)
        task1 = asyncio.ensure_future(sess.send_and_wait("cmd1", timeout=0.05))
        await asyncio.sleep(0.01)  # let it start

        # Second send_and_wait should raise
        with pytest.raises(RuntimeError, match="already pending"):
            await sess.send_and_wait("cmd2")

        await task1  # let it finish (timeout)
    await sess.close()


async def test_send_and_wait_raises_when_closed() -> None:
    sess = _make_session()
    await sess.close()
    with pytest.raises(SessionClosed):
        await sess.send_and_wait("echo x")


# --- AsyncSession.read ---


async def test_read_drains_output() -> None:
    frames = [
        (STREAM_STDOUT, b"line 1\n"),
        (STREAM_STDOUT, b"line 2\n"),
    ]
    sess = _make_session(frames)
    # Give the read loop time to process
    await asyncio.sleep(0.05)

    text = sess.read()
    assert "line 1\n" in text
    assert "line 2\n" in text

    # Second read should be empty
    assert sess.read() == ""
    await sess.close()


async def test_read_includes_stderr() -> None:
    frames = [
        (STREAM_STDERR, b"err msg"),
    ]
    sess = _make_session(frames)
    await asyncio.sleep(0.05)

    text = sess.read()
    assert "err msg" in text
    await sess.close()


# --- AsyncSession.on_output ---


async def test_on_output_callback_fires() -> None:
    frames = [
        (STREAM_STDOUT, b"data\n"),
    ]
    captured: list[str] = []
    sess = _make_session(frames)
    sess.on_output(captured.append)
    await asyncio.sleep(0.05)

    assert any("data" in c for c in captured)
    await sess.close()


async def test_on_output_callback_error_suppressed() -> None:
    frames = [
        (STREAM_STDOUT, b"ok\n"),
    ]
    sess = _make_session(frames)
    sess.on_output(lambda _text: 1 / 0)  # will raise ZeroDivisionError
    await asyncio.sleep(0.05)
    # Should not crash — error is suppressed
    assert sess.read() != ""
    await sess.close()


# --- AsyncSession.close ---


async def test_close_is_idempotent() -> None:
    sess = _make_session()
    await sess.close()
    await sess.close()  # should not raise


async def test_close_cancels_read_task() -> None:
    async def _infinite_gen() -> AsyncGenerator[tuple[int, bytes], None]:
        while True:
            await asyncio.sleep(1)
            yield (STREAM_STDOUT, b"tick\n")

    writer = _mock_writer()
    sess = AsyncSession("eid", _infinite_gen(), writer, "/tmp/s.sock", "cid")
    assert not sess._task.done()

    await sess.close()
    assert sess._task.done()


# --- AsyncSession.id ---


async def test_session_id_property() -> None:
    sess = _make_session()
    assert sess.id == "eid"
    await sess.close()


# --- Unexpected EOF signals pending command ---


async def test_unexpected_eof_signals_pending() -> None:
    uuid_hex = "e" * 16
    gate = asyncio.Event()
    # Empty frames — EOF after gate is released
    frames: list[tuple[int, bytes]] = []
    writer = _mock_writer()
    sess = AsyncSession("eid", _delayed_gen(frames, gate), writer, "/tmp/s.sock", "cid")

    with patch("pocket_dock._session.uuid.uuid4") as mock_uuid:
        mock_uuid.return_value = MagicMock(hex=uuid_hex + "extrastuff")
        task = asyncio.ensure_future(sess.send_and_wait("echo x"))
        await asyncio.sleep(0.01)
        gate.set()  # release — read loop hits EOF with pending command
        result = await task

    assert result.exit_code == -1
    await sess.close()


# --- Sentinel filtering ---


async def test_sentinel_not_in_general_output() -> None:
    uuid_hex = "f" * 16
    sentinel_line = f"__PD_{uuid_hex}_0__"
    gate = asyncio.Event()
    frames = [
        (STREAM_STDOUT, b"real output\n"),
        (STREAM_STDOUT, f"{sentinel_line}\n".encode()),
    ]
    writer = _mock_writer()
    sess = AsyncSession("eid", _delayed_gen(frames, gate), writer, "/tmp/s.sock", "cid")

    with patch("pocket_dock._session.uuid.uuid4") as mock_uuid:
        mock_uuid.return_value = MagicMock(hex=uuid_hex + "extrastuff")
        task = asyncio.ensure_future(sess.send_and_wait("echo real output"))
        await asyncio.sleep(0.01)
        gate.set()
        result = await task

    assert result.exit_code == 0
    # Sentinel should NOT appear in the general output buffer
    remaining = sess.read()
    assert "__PD_" not in remaining
    await sess.close()


# --- _check_sentinel edge cases ---


async def test_check_sentinel_no_pending() -> None:
    sess = _make_session()
    # No pending command — should return False
    assert sess._check_sentinel("__PD_abcdef0123456789_0__") is False
    await sess.close()


async def test_check_sentinel_wrong_uuid() -> None:
    sess = _make_session()
    # Set up a pending with different UUID
    sess._pending = _PendingCommand("1111111111111111", asyncio.Event(), time.monotonic())
    assert sess._check_sentinel("__PD_2222222222222222_0__") is False
    sess._pending.event.set()
    sess._pending = None
    await sess.close()


# --- Container.session() wiring ---


async def test_async_container_session() -> None:
    from pocket_dock._async_container import AsyncContainer

    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-test")
    writer = _mock_writer()
    frames: list[tuple[int, bytes]] = []

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list(frames), writer),
        ),
    ):
        sess = await ac.session()

    assert isinstance(sess, AsyncSession)
    assert sess in ac._active_sessions
    await sess.close()


async def test_async_container_shutdown_cleans_sessions() -> None:
    from pocket_dock._async_container import AsyncContainer

    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-test")
    writer = _mock_writer()

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list([]), writer),
        ),
    ):
        await ac.session()

    with (
        patch("pocket_dock._async_container.sc.stop_container", new_callable=AsyncMock),
        patch("pocket_dock._async_container.sc.remove_container", new_callable=AsyncMock),
    ):
        await ac.shutdown()

    assert len(ac._active_sessions) == 0


# --- SyncSession ---


def test_sync_session_send_and_wait() -> None:
    """Test SyncSession delegates send_and_wait to the async session."""
    lt = _LoopThread.get()
    expected = ExecResult(exit_code=0, stdout="sync result\n", stderr="", duration_ms=1.0)
    async_session = MagicMock()
    async_session.send_and_wait = AsyncMock(return_value=expected)
    async_session.send = AsyncMock()
    async_session.close = AsyncMock()

    sess = SyncSession(async_session, lt)
    result = sess.send_and_wait("echo sync result")

    assert result.exit_code == 0
    assert result.stdout == "sync result\n"
    async_session.send_and_wait.assert_awaited_once_with(
        "echo sync result",
        timeout=None,
    )
    sess.close()
    async_session.close.assert_awaited()


def test_sync_session_via_container() -> None:
    from pocket_dock._async_container import AsyncContainer

    ac = AsyncContainer("cid", "/tmp/s.sock", name="pd-test")
    lt = _LoopThread.get()
    c = Container(ac, lt)
    writer = _mock_writer()

    with (
        patch(
            "pocket_dock._async_container.sc._exec_create",
            new_callable=AsyncMock,
            return_value="eid",
        ),
        patch(
            "pocket_dock._async_container.sc._exec_start_stream",
            new_callable=AsyncMock,
            return_value=(_gen_from_list([]), writer),
        ),
    ):
        sess = c.session()

    assert isinstance(sess, SyncSession)
    assert sess.id == "eid"
    sess.close()


def test_sync_session_read() -> None:
    lt = _LoopThread.get()
    async_session = MagicMock()
    async_session.read = MagicMock(return_value="output\n")
    async_session.close = AsyncMock()

    sess = SyncSession(async_session, lt)
    text = sess.read()
    assert text == "output\n"
    async_session.read.assert_called_once()
    sess.close()


def test_sync_session_on_output() -> None:
    lt = _LoopThread.get()
    async_session = MagicMock()
    async_session.close = AsyncMock()
    captured: list[str] = []

    sess = SyncSession(async_session, lt)
    sess.on_output(captured.append)
    async_session.on_output.assert_called_once_with(captured.append)
    sess.close()


def test_sync_session_send() -> None:
    lt = _LoopThread.get()
    async_session = MagicMock()
    async_session.send = AsyncMock()
    async_session.close = AsyncMock()

    sess = SyncSession(async_session, lt)
    sess.send("echo hi")
    async_session.send.assert_awaited_once_with("echo hi")
    sess.close()


# --- Exports ---


def test_exports_session_alias() -> None:
    from pocket_dock import Session

    assert Session is SyncSession


def test_exports_session_closed_error() -> None:
    from pocket_dock import SessionClosed as ExportedError

    assert ExportedError is SessionClosed


def test_exports_async_session() -> None:
    from pocket_dock.async_ import AsyncSession as ExportedSession

    assert ExportedSession is AsyncSession
