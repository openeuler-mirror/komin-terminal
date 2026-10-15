"""Shared fixtures for the database layer test suite (SQLite only)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from komin_terminal.config import DatabaseConfig
from komin_terminal.daemon.database import DatabaseManager


@pytest.fixture
def db_manager(tmp_path: Path) -> Iterator[DatabaseManager]:
    """Provide an initialized SQLite-backed DatabaseManager.

    The database file lives under ``tmp_path`` and the manager is disposed
    at teardown.

    Args:
        tmp_path: Per-test temporary directory.

    Yields:
        An initialized :class:`DatabaseManager`.
    """
    config = DatabaseConfig(type="sqlite", sqlite_path=tmp_path / "test.db")
    manager = DatabaseManager(config)
    manager.initialize()
    yield manager
    manager.dispose()


@pytest.fixture
def user_a() -> uuid.UUID:
    """First isolated test user."""
    return uuid.uuid4()


@pytest.fixture
def user_b() -> uuid.UUID:
    """Second isolated test user."""
    return uuid.uuid4()
