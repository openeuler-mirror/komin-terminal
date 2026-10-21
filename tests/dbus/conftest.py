"""Shared fixtures for the D-Bus layer test suite (fully offline)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from komin_terminal.config import DatabaseConfig
from komin_terminal.daemon.database import DatabaseManager
from komin_terminal.daemon.session import UserSessionManager
from komin_terminal.dbus.interfaces import Authorization, ChatInterface, HistoryInterface
from tests.dbus.fakes import FakeBus, FakeQueryExecutor

CALLER_A: str = ":1.1"
CALLER_B: str = ":1.2"
UID_A: int = 1000
UID_B: int = 1001
DEFAULT_MODEL: str = "test-model"


@pytest.fixture
def db_manager(tmp_path: Path) -> Iterator[DatabaseManager]:
    """Provide an initialized SQLite-backed DatabaseManager.

    Args:
        tmp_path: Per-test temporary directory.

    Yields:
        An initialized :class:`DatabaseManager`, disposed at teardown.
    """
    config = DatabaseConfig(type="sqlite", sqlite_path=tmp_path / "test.db")
    manager = DatabaseManager(config)
    manager.initialize()
    yield manager
    manager.dispose()


@pytest.fixture
def sessions(xdg_env: Path) -> UserSessionManager:
    """Provide a session manager over the fake machine-id.

    Args:
        xdg_env: Filesystem isolation fixture root.

    Returns:
        A fresh :class:`UserSessionManager`.
    """
    del xdg_env
    return UserSessionManager()


@pytest.fixture
def bus() -> FakeBus:
    """Provide a caller-prepared in-memory bus.

    Returns:
        A :class:`FakeBus` with both test users registered.
    """
    fake = FakeBus()
    fake.set_caller_uid(CALLER_A, UID_A)
    fake.set_caller_uid(CALLER_B, UID_B)
    fake.caller = CALLER_A
    return fake


@pytest.fixture
def user_a(sessions: UserSessionManager) -> uuid.UUID:
    """Stable user id of the first test user."""
    return sessions.get_user_id(UID_A)


@pytest.fixture
def user_b(sessions: UserSessionManager) -> uuid.UUID:
    """Stable user id of the second test user."""
    return sessions.get_user_id(UID_B)


@pytest.fixture
def auth(bus: FakeBus, sessions: UserSessionManager) -> Authorization:
    """Provide the authorizer over the fake bus."""
    return Authorization(bus, sessions)


@pytest.fixture
def executor() -> FakeQueryExecutor:
    """Provide the programmable fake executor."""
    return FakeQueryExecutor()


@pytest.fixture
def chat_interface(
    auth: Authorization,
    sessions: UserSessionManager,
    db_manager: DatabaseManager,
    executor: FakeQueryExecutor,
    bus: FakeBus,
) -> ChatInterface:
    """Provide the chat service under test."""
    return ChatInterface(
        auth=auth,
        sessions=sessions,
        db=db_manager,
        executor_factory=lambda: executor,
        bus=bus,
        default_model=DEFAULT_MODEL,
    )


@pytest.fixture
def history_interface(
    auth: Authorization,
    sessions: UserSessionManager,
    db_manager: DatabaseManager,
    bus: FakeBus,
) -> HistoryInterface:
    """Provide the history service under test."""
    return HistoryInterface(auth=auth, sessions=sessions, db=db_manager, bus=bus)
