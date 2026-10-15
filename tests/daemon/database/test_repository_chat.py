"""Tests for ChatRepository.get_by_name."""

from __future__ import annotations

import uuid

from komin_terminal.daemon.database import ChatRepository, DatabaseManager


def test_get_by_name_hit(db_manager: DatabaseManager, user_a: uuid.UUID) -> None:
    """get_by_name returns the user's live chat with that name."""
    repo = ChatRepository(db_manager, user_a)
    repo.add(name="chat-a")
    record = repo.get_by_name("chat-a")
    assert record is not None
    assert record.name == "chat-a"


def test_get_by_name_miss(db_manager: DatabaseManager, user_a: uuid.UUID) -> None:
    """get_by_name returns None for an unknown name."""
    repo = ChatRepository(db_manager, user_a)
    repo.add(name="chat-a")
    assert repo.get_by_name("chat-b") is None


def test_get_by_name_soft_deleted_miss(db_manager: DatabaseManager, user_a: uuid.UUID) -> None:
    """get_by_name ignores soft-deleted chats."""
    repo = ChatRepository(db_manager, user_a)
    record = repo.add(name="chat-a")
    assert repo.soft_delete(record.id)
    assert repo.get_by_name("chat-a") is None


def test_get_by_name_scoped_to_user(
    db_manager: DatabaseManager, user_a: uuid.UUID, user_b: uuid.UUID
) -> None:
    """get_by_name never crosses user boundaries."""
    ChatRepository(db_manager, user_a).add(name="shared-name")
    assert ChatRepository(db_manager, user_b).get_by_name("shared-name") is None
