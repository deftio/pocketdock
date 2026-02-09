"""Tests for CallbackRegistry."""

from __future__ import annotations

from pocket_dock._callbacks import CallbackRegistry

# --- Registration and dispatch ---


def test_stdout_callback_fires() -> None:
    reg = CallbackRegistry()
    captured: list[tuple[object, str]] = []
    reg.on_stdout(lambda c, d: captured.append((c, d)))
    reg.dispatch_stdout("container", "hello")
    assert captured == [("container", "hello")]


def test_stderr_callback_fires() -> None:
    reg = CallbackRegistry()
    captured: list[tuple[object, str]] = []
    reg.on_stderr(lambda c, d: captured.append((c, d)))
    reg.dispatch_stderr("container", "error")
    assert captured == [("container", "error")]


def test_exit_callback_fires() -> None:
    reg = CallbackRegistry()
    captured: list[tuple[object, int]] = []
    reg.on_exit(lambda c, code: captured.append((c, code)))
    reg.dispatch_exit("container", 0)
    assert captured == [("container", 0)]


def test_multiple_callbacks_same_event() -> None:
    reg = CallbackRegistry()
    calls: list[int] = []
    reg.on_stdout(lambda _c, _d: calls.append(1))
    reg.on_stdout(lambda _c, _d: calls.append(2))
    reg.dispatch_stdout("c", "data")
    assert calls == [1, 2]


# --- No callbacks registered ---


def test_dispatch_no_callbacks_is_noop() -> None:
    reg = CallbackRegistry()
    # Should not raise
    reg.dispatch_stdout("c", "data")
    reg.dispatch_stderr("c", "data")
    reg.dispatch_exit("c", 0)


# --- Error suppression ---


def test_callback_error_suppressed_stdout() -> None:
    reg = CallbackRegistry()
    calls: list[str] = []

    def bad_callback(_c: object, _d: str) -> None:
        msg = "boom"
        raise RuntimeError(msg)

    reg.on_stdout(bad_callback)
    reg.on_stdout(lambda _c, d: calls.append(d))
    reg.dispatch_stdout("c", "hello")
    # Second callback still fires despite first raising
    assert calls == ["hello"]


def test_callback_error_suppressed_stderr() -> None:
    reg = CallbackRegistry()
    calls: list[str] = []

    def bad_callback(_c: object, _d: str) -> None:
        msg = "boom"
        raise RuntimeError(msg)

    reg.on_stderr(bad_callback)
    reg.on_stderr(lambda _c, d: calls.append(d))
    reg.dispatch_stderr("c", "err")
    assert calls == ["err"]


def test_callback_error_suppressed_exit() -> None:
    reg = CallbackRegistry()
    calls: list[int] = []

    def bad_callback(_c: object, _code: int) -> None:
        msg = "boom"
        raise RuntimeError(msg)

    reg.on_exit(bad_callback)
    reg.on_exit(lambda _c, code: calls.append(code))
    reg.dispatch_exit("c", 42)
    assert calls == [42]
