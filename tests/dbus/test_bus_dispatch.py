"""Regression tests for the client-side signal dispatch loop (F-9).

GLib only delivers subscribed signal callbacks while a main loop iterates
the connection's context. The daemon runs ``run_forever`` on its main
thread, but the CLI client has no such loop; :class:`SystemBusBackend`
therefore starts a background dispatch loop on first subscription. These
tests exercise that loop management without touching a real bus.
"""

from __future__ import annotations

import pytest

gi = pytest.importorskip("gi", reason="pygobject required for dispatch-loop tests")

from komin_terminal.dbus.bus import SystemBusBackend  # noqa: E402


def _bare_backend() -> SystemBusBackend:
    backend = object.__new__(SystemBusBackend)
    backend._loop = None
    backend._dispatch_loop = None
    backend._dispatch_thread = None
    return backend


def test_ensure_dispatch_loop_starts_background_thread() -> None:
    backend = _bare_backend()

    backend._ensure_dispatch_loop()

    thread = backend._dispatch_thread
    loop = backend._dispatch_loop
    assert thread is not None
    assert loop is not None
    assert thread.is_alive()

    loop.quit()
    thread.join(timeout=2)
    assert not thread.is_alive()


def test_ensure_dispatch_loop_is_idempotent() -> None:
    backend = _bare_backend()

    backend._ensure_dispatch_loop()
    first_thread = backend._dispatch_thread
    first_loop = backend._dispatch_loop

    backend._ensure_dispatch_loop()

    assert backend._dispatch_thread is first_thread
    assert backend._dispatch_loop is first_loop

    first_loop.quit()
    first_thread.join(timeout=2)


def test_ensure_dispatch_loop_skipped_when_main_loop_present() -> None:
    backend = _bare_backend()
    backend._loop = object()  # simulate run_forever already owning a loop

    backend._ensure_dispatch_loop()

    assert backend._dispatch_thread is None
    assert backend._dispatch_loop is None
