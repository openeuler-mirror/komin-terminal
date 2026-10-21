"""Tests for the history service interface."""

from __future__ import annotations

import uuid

import pytest
from komin_terminal.daemon.database import (
    ChatRepository,
    DatabaseManager,
    HistoryRepository,
    InteractionRepository,
)
from komin_terminal.daemon.session import UserSessionManager
from komin_terminal.dbus.interfaces import HistoryInterface
from tests.dbus.conftest import CALLER_A, CALLER_B, UID_A


def _seed_interaction(
    db_manager: DatabaseManager,
    user_id: uuid.UUID,
    *,
    chat_id: uuid.UUID | None,
    question: str,
    response: str,
) -> uuid.UUID:
    history = HistoryRepository(db_manager, user_id).add(chat_id=chat_id)
    interaction = InteractionRepository(db_manager, user_id).append_interaction(
        history.id, question, response, "test-model", 0
    )
    return interaction.id


def test_get_history_keyword_filter_and_pagination(
    history_interface: HistoryInterface,
    db_manager: DatabaseManager,
    sessions: UserSessionManager,
) -> None:
    user_id = sessions.get_user_id(UID_A)
    chat = ChatRepository(db_manager, user_id).add(name="ops")
    _seed_interaction(db_manager, user_id, chat_id=chat.id, question="alpha one", response="r1")
    _seed_interaction(db_manager, user_id, chat_id=chat.id, question="beta two", response="r2")
    _seed_interaction(db_manager, user_id, chat_id=None, question="alpha three", response="r3")

    everything = history_interface.get_history("", 0, 50, CALLER_A)
    assert len(everything) == 3
    assert all("question" in entry and "response" in entry for entry in everything)

    alphas = history_interface.get_history("alpha", 0, 50, CALLER_A)
    assert sorted(entry["question"] for entry in alphas) == ["alpha one", "alpha three"]

    paged = history_interface.get_history("", 0, 2, CALLER_A)
    assert len(paged) == 2
    offset = history_interface.get_history("", 2, 2, CALLER_A)
    assert len(offset) == 1
    assert paged[0]["id"] != offset[0]["id"]


def test_clear_history_everything(
    history_interface: HistoryInterface,
    db_manager: DatabaseManager,
    sessions: UserSessionManager,
) -> None:
    user_id = sessions.get_user_id(UID_A)
    _seed_interaction(db_manager, user_id, chat_id=None, question="q1", response="r1")
    _seed_interaction(db_manager, user_id, chat_id=None, question="q2", response="r2")

    assert history_interface.clear_history("", CALLER_A) is True
    assert history_interface.get_history("", 0, 50, CALLER_A) == []
    assert history_interface.clear_history("", CALLER_A) is False


def test_clear_history_by_chat(
    history_interface: HistoryInterface,
    db_manager: DatabaseManager,
    sessions: UserSessionManager,
) -> None:
    user_id = sessions.get_user_id(UID_A)
    kept_chat = ChatRepository(db_manager, user_id).add(name="kept")
    cleared_chat = ChatRepository(db_manager, user_id).add(name="cleared")
    _seed_interaction(db_manager, user_id, chat_id=kept_chat.id, question="keep", response="r")
    _seed_interaction(db_manager, user_id, chat_id=cleared_chat.id, question="drop", response="r")

    assert history_interface.clear_history(str(cleared_chat.id), CALLER_A) is True

    remaining = history_interface.get_history("", 0, 50, CALLER_A)
    assert [entry["question"] for entry in remaining] == ["keep"]
    assert history_interface.clear_history(str(cleared_chat.id), CALLER_A) is False


def test_clear_history_unknown_chat_returns_false(history_interface: HistoryInterface) -> None:
    assert history_interface.clear_history(str(uuid.uuid4()), CALLER_A) is False
    with pytest.raises(KeyError):
        history_interface.clear_history("not-a-uuid", CALLER_A)


def test_get_interaction_and_cross_user_isolation(
    history_interface: HistoryInterface,
    db_manager: DatabaseManager,
    sessions: UserSessionManager,
) -> None:
    user_a = sessions.get_user_id(UID_A)
    interaction_id = _seed_interaction(
        db_manager, user_a, chat_id=None, question="secret", response="answer"
    )

    entry = history_interface.get_interaction(str(interaction_id), CALLER_A)
    assert entry["id"] == str(interaction_id)
    assert entry["question"] == "secret"

    with pytest.raises(KeyError):
        history_interface.get_interaction(str(interaction_id), CALLER_B)
    assert history_interface.get_history("", 0, 50, CALLER_B) == []


def test_get_interaction_unknown_id(history_interface: HistoryInterface) -> None:
    with pytest.raises(KeyError):
        history_interface.get_interaction(str(uuid.uuid4()), CALLER_A)
    with pytest.raises(KeyError):
        history_interface.get_interaction("not-a-uuid", CALLER_A)
