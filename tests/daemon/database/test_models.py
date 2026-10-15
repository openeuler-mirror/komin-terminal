"""Tests for ORM model defaults, timestamps and soft-delete semantics."""

from __future__ import annotations

import time
import uuid
from datetime import timedelta

from komin_terminal.daemon.database import (
    ChatModel,
    DatabaseManager,
    HistoryModel,
    InteractionModel,
)


def test_chat_model_defaults(db_manager: DatabaseManager, user_a: uuid.UUID) -> None:
    """ChatModel gets a UUID pk, empty strings and UTC timestamps."""
    chat = ChatModel(user_id=user_a, name="hello")
    with db_manager.session() as session:
        session.add(chat)
    assert isinstance(chat.id, uuid.UUID)
    assert chat.description == ""
    assert chat.model == ""
    assert chat.created_at.tzinfo is not None
    assert chat.created_at.utcoffset() == timedelta(0)
    assert chat.updated_at.tzinfo is not None
    assert chat.deleted_at is None
    assert not chat.is_deleted


def test_history_model_defaults(db_manager: DatabaseManager, user_a: uuid.UUID) -> None:
    """HistoryModel leaves chat_id NULL unless attached to a chat."""
    history = HistoryModel(user_id=user_a)
    with db_manager.session() as session:
        session.add(history)
    assert history.chat_id is None
    assert history.created_at.tzinfo is not None


def test_interaction_model_defaults(db_manager: DatabaseManager, user_a: uuid.UUID) -> None:
    """InteractionModel defaults to empty response/model and zero tokens."""
    history = HistoryModel(user_id=user_a)
    with db_manager.session() as session:
        session.add(history)
        session.flush()
        interaction = InteractionModel(history_id=history.id, question="q")
        session.add(interaction)
    assert interaction.response == ""
    assert interaction.model == ""
    assert interaction.tokens_used == 0
    assert interaction.created_at.tzinfo is not None


def test_is_deleted_flag(db_manager: DatabaseManager, user_a: uuid.UUID) -> None:
    """is_deleted tracks the presence of deleted_at."""
    chat = ChatModel(user_id=user_a, name="flag")
    with db_manager.session() as session:
        session.add(chat)
    assert not chat.is_deleted
    chat.deleted_at = chat.updated_at
    assert chat.is_deleted


def test_updated_at_refreshes_on_change(db_manager: DatabaseManager, user_a: uuid.UUID) -> None:
    """Modifying a row refreshes updated_at while created_at stays stable."""
    chat = ChatModel(user_id=user_a, name="before")
    with db_manager.session() as session:
        session.add(chat)
    created_before = chat.created_at
    updated_before = chat.updated_at
    time.sleep(0.001)
    with db_manager.session() as session:
        merged = session.merge(chat)
        merged.name = "after"
    assert merged.updated_at > updated_before
    assert merged.created_at == created_before


def test_touch_updated_manually(db_manager: DatabaseManager, user_a: uuid.UUID) -> None:
    """touch_updated() bumps updated_at explicitly."""
    chat = ChatModel(user_id=user_a, name="touch")
    with db_manager.session() as session:
        session.add(chat)
    before = chat.updated_at
    time.sleep(0.001)
    chat.touch_updated()
    assert chat.updated_at > before
