"""Tests for the D-Bus server container (FakeBus only)."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from komin_terminal.config import (
    BackendConfig,
    DatabaseConfig,
    DisplayConfig,
    KominConfig,
    LoggingConfig,
)
from komin_terminal.constants import (
    get_dbus_chat_namespace,
    get_dbus_history_namespace,
    get_dbus_object_path_chat,
    get_dbus_object_path_history,
    get_dbus_object_path_user,
    get_dbus_user_namespace,
)
from komin_terminal.daemon.database import DatabaseManager
from komin_terminal.dbus.server import KominDBusServer
from tests.dbus.fakes import FakeBus, wait_until


def _config(tmp_path: Path) -> KominConfig:
    return KominConfig(
        backend=BackendConfig(url="http://localhost:8000/v1", api_key="sk-test", model="m"),
        database=DatabaseConfig(type="sqlite", sqlite_path=tmp_path / "komind.db"),
        display=DisplayConfig(),
        logging=LoggingConfig(),
    )


def test_start_registers_three_paths_and_names(xdg_env: Path) -> None:
    fake = FakeBus()
    server = KominDBusServer(_config(xdg_env), bus=fake)
    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()
    try:
        assert wait_until(lambda: len(fake.requested_names) == 3)
        assert set(fake.published_objects) == {
            get_dbus_object_path_chat(),
            get_dbus_object_path_history(),
            get_dbus_object_path_user(),
        }
        assert set(fake.requested_names) == {
            get_dbus_chat_namespace(),
            get_dbus_history_namespace(),
            get_dbus_user_namespace(),
        }
    finally:
        server.stop()
        thread.join(timeout=2)
    assert not thread.is_alive()
    assert fake.disconnected is True


def test_stop_is_idempotent_and_disposes_database(
    xdg_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    disposed: list[bool] = []
    original_dispose = DatabaseManager.dispose

    def spy(self: DatabaseManager) -> None:
        disposed.append(True)
        original_dispose(self)

    monkeypatch.setattr(DatabaseManager, "dispose", spy)

    fake = FakeBus()
    server = KominDBusServer(_config(xdg_env), bus=fake)
    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()
    assert wait_until(lambda: len(fake.requested_names) == 3)

    server.stop()
    thread.join(timeout=2)
    assert disposed == [True]

    server.stop()
    server.stop()
    assert disposed == [True]


def test_double_start_raises(xdg_env: Path) -> None:
    fake = FakeBus()
    server = KominDBusServer(_config(xdg_env), bus=fake)
    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()
    try:
        assert wait_until(lambda: len(fake.requested_names) == 3)
        with pytest.raises(RuntimeError):
            server.start()
    finally:
        server.stop()
        thread.join(timeout=2)


def test_stop_before_start_is_safe(xdg_env: Path) -> None:
    server = KominDBusServer(_config(xdg_env), bus=FakeBus())
    server.stop()
