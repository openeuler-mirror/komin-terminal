"""Tests for DatabaseManager lifecycle, sessions and error conversion."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from komin_terminal.config import DatabaseConfig
from komin_terminal.daemon.database import ChatModel, DatabaseManager
from komin_terminal.daemon.database.models import SchemaVersion
from komin_terminal.exceptions import DatabaseError
from sqlalchemy import select


def test_initialize_is_idempotent(db_manager: DatabaseManager) -> None:
    """Calling initialize twice must not raise or recreate the engine."""
    engine_before = db_manager._engine
    db_manager.initialize()
    assert db_manager._engine is engine_before


def test_session_commits(db_manager: DatabaseManager, user_a: uuid.UUID) -> None:
    """A successful session body commits its writes."""
    with db_manager.session() as session:
        session.add(ChatModel(user_id=user_a, name="committed"))
    with db_manager.session() as session:
        names = list(session.scalars(select(ChatModel.name)))
    assert names == ["committed"]


def test_session_rolls_back_and_raises_database_error(
    db_manager: DatabaseManager, user_a: uuid.UUID
) -> None:
    """A conflicting PK write rolls back and surfaces as DatabaseError."""
    fixed_id = uuid.uuid4()
    with db_manager.session() as session:
        session.add(ChatModel(id=fixed_id, user_id=user_a, name="first"))
    with pytest.raises(DatabaseError), db_manager.session() as session:
        session.add(ChatModel(id=fixed_id, user_id=user_a, name="duplicate"))
    with db_manager.session() as session:
        names = list(session.scalars(select(ChatModel.name)))
    assert names == ["first"]


def test_session_before_initialize_raises_database_error(tmp_path: Path) -> None:
    """Sessions require a prior initialize call."""
    manager = DatabaseManager(DatabaseConfig(type="sqlite", sqlite_path=tmp_path / "x.db"))
    with pytest.raises(DatabaseError), manager.session():
        pass  # pragma: no cover


def test_initialize_failure_raises_database_error(tmp_path: Path) -> None:
    """An unusable sqlite path converts engine failure to DatabaseError."""
    manager = DatabaseManager(
        DatabaseConfig(type="sqlite", sqlite_path=tmp_path / "missing" / "sub" / "x.db")
    )
    with pytest.raises(DatabaseError):
        manager.initialize()


def test_dispose_allows_reinitialize(tmp_path: Path) -> None:
    """After dispose a new engine can be created on the same file."""
    config = DatabaseConfig(type="sqlite", sqlite_path=tmp_path / "reinit.db")
    manager = DatabaseManager(config)
    manager.initialize()
    manager.dispose()
    manager.initialize()
    assert manager.is_initialized
    with manager.session() as session:
        session.add(ChatModel(user_id=uuid.uuid4(), name="after-reinit"))
    with manager.session() as session:
        names = list(session.scalars(select(ChatModel.name)))
    assert names == ["after-reinit"]


def test_schema_version_seeded(db_manager: DatabaseManager) -> None:
    """The schema_version table contains a single row with value 1."""
    with db_manager.session() as session:
        versions = list(session.scalars(select(SchemaVersion.version)))
    assert versions == [1]


def test_schema_version_seeded_once(db_manager: DatabaseManager) -> None:
    """Re-initialization does not duplicate the schema_version row."""
    db_manager.initialize()
    with db_manager.session() as session:
        versions = list(session.scalars(select(SchemaVersion.version)))
    assert versions == [1]
