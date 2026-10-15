"""Tests for HistoryRepository and InteractionRepository."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

import pytest
from komin_terminal.daemon.database import (
    ChatRepository,
    DatabaseManager,
    HistoryModel,
    HistoryRepository,
    InteractionModel,
    InteractionRepository,
)
from komin_terminal.exceptions import DatabaseError

_UTC = UTC


def _make_histories(
    db_manager: DatabaseManager, user_a: uuid.UUID,
) -> tuple[HistoryModel, HistoryModel]:
    """Create two chats, each with one history record."""
    chat_repo = ChatRepository(db_manager, user_a)
    chat_1 = chat_repo.add(name="chat-1")
    chat_2 = chat_repo.add(name="chat-2")
    repo = HistoryRepository(db_manager, user_a)
    return repo.add(chat_id=chat_1.id), repo.add(chat_id=chat_2.id)


def test_list_by_chat_filters(db_manager: DatabaseManager, user_a: uuid.UUID) -> None:
    """list_by_chat only returns histories attached to the given chat."""
    history_1, _ = _make_histories(db_manager, user_a)
    repo = HistoryRepository(db_manager, user_a)
    result = repo.list_by_chat(history_1.chat_id)
    assert [record.id for record in result] == [history_1.id]


def test_list_by_chat_newest_first(db_manager: DatabaseManager, user_a: uuid.UUID) -> None:
    """list_by_chat orders by created_at descending."""
    chat = ChatRepository(db_manager, user_a).add(name="chat")
    repo = HistoryRepository(db_manager, user_a)
    first = repo.add(chat_id=chat.id)
    time.sleep(0.001)
    second = repo.add(chat_id=chat.id)
    result = repo.list_by_chat(chat.id)
    assert [record.id for record in result] == [second.id, first.id]


def test_list_by_chat_pagination(db_manager: DatabaseManager, user_a: uuid.UUID) -> None:
    """list_by_chat honours offset/limit."""
    chat = ChatRepository(db_manager, user_a).add(name="chat")
    repo = HistoryRepository(db_manager, user_a)
    repo.add(chat_id=chat.id)
    repo.add(chat_id=chat.id)
    result = repo.list_by_chat(chat.id, offset=1, limit=1)
    assert len(result) == 1


def test_list_by_chat_cross_user(
    db_manager: DatabaseManager,
    user_a: uuid.UUID,
    user_b: uuid.UUID,
) -> None:
    """list_by_chat never returns another user's histories."""
    history_1, _ = _make_histories(db_manager, user_a)
    repo_b = HistoryRepository(db_manager, user_b)
    assert repo_b.list_by_chat(history_1.chat_id) == []


def test_filter_keyword_case_insensitive(db_manager: DatabaseManager, user_a: uuid.UUID) -> None:
    """keyword matching is case-insensitive over question and response."""
    history = HistoryRepository(db_manager, user_a).add()
    repo = InteractionRepository(db_manager, user_a)
    repo.append_interaction(history.id, "How do I restart sshd?", "Use systemctl", "gpt", 10)
    repo.append_interaction(history.id, "disk full", "Free space", "gpt", 5)
    assert len(repo.filter(keyword="restart")) == 1
    assert len(repo.filter(keyword="RESTART")) == 1
    assert len(repo.filter(keyword="free")) == 1
    assert len(repo.filter(keyword="systemctl")) == 1
    assert repo.filter(keyword="no-match") == []


def test_filter_since_until_boundaries(db_manager: DatabaseManager, user_a: uuid.UUID) -> None:
    """since/until are inclusive boundaries on created_at (UTC)."""
    history = HistoryRepository(db_manager, user_a).add()
    repo = InteractionRepository(db_manager, user_a)
    t1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=_UTC)
    t2 = datetime(2026, 1, 2, 12, 0, 0, tzinfo=_UTC)
    t3 = datetime(2026, 1, 3, 12, 0, 0, tzinfo=_UTC)
    repo.add(history_id=history.id, question="first", created_at=t1)
    b = repo.add(history_id=history.id, question="second", created_at=t2)
    c = repo.add(history_id=history.id, question="third", created_at=t3)
    assert [r.id for r in repo.filter(since=t2, until=t3)] == [c.id, b.id]
    assert len(repo.filter(since=t1, until=t1)) == 1
    assert [r.id for r in repo.filter(since=t2)] == [c.id, b.id]
    assert len(repo.filter(until=t2)) == 2


def test_filter_combined_conditions(db_manager: DatabaseManager, user_a: uuid.UUID) -> None:
    """keyword + since + until can be combined."""
    history = HistoryRepository(db_manager, user_a).add()
    repo = InteractionRepository(db_manager, user_a)
    t1 = datetime(2026, 2, 1, 8, 0, 0, tzinfo=_UTC)
    t2 = datetime(2026, 2, 2, 8, 0, 0, tzinfo=_UTC)
    repo.add(history_id=history.id, question="alpha one", created_at=t1)
    repo.add(history_id=history.id, question="alpha two", created_at=t2)
    result = repo.filter(keyword="alpha", since=t1, until=t2)
    assert len(result) == 2


def test_filter_cross_user_isolation(
    db_manager: DatabaseManager, user_a: uuid.UUID, user_b: uuid.UUID
) -> None:
    """user_b's filter never sees user_a's interactions."""
    history_a = HistoryRepository(db_manager, user_a).add()
    InteractionRepository(db_manager, user_a).append_interaction(
        history_a.id, "secret question", "secret answer", "gpt", 10
    )
    repo_b = InteractionRepository(db_manager, user_b)
    assert repo_b.filter() == []
    assert repo_b.filter(keyword="secret") == []
    assert repo_b.filter(since=datetime(2020, 1, 1, tzinfo=_UTC)) == []
    assert repo_b.count() == 0


def test_filter_respects_soft_delete(db_manager: DatabaseManager, user_a: uuid.UUID) -> None:
    """Soft-deleted interactions are excluded from filter."""
    history = HistoryRepository(db_manager, user_a).add()
    repo = InteractionRepository(db_manager, user_a)
    interaction = repo.append_interaction(history.id, "visible", "answer", "gpt", 3)
    repo.add(history_id=history.id, question="hidden")
    assert repo.soft_delete(interaction.id)
    result = repo.filter(keyword="visible")
    assert result == []


def test_filter_newest_first(db_manager: DatabaseManager, user_a: uuid.UUID) -> None:
    """filter orders by created_at descending."""
    history = HistoryRepository(db_manager, user_a).add()
    repo = InteractionRepository(db_manager, user_a)
    first = repo.append_interaction(history.id, "q1", "a1", "gpt", 1)
    time.sleep(0.001)
    second = repo.append_interaction(history.id, "q2", "a2", "gpt", 2)
    assert [r.id for r in repo.filter()] == [second.id, first.id]


def test_append_interaction_persists_fields(
    db_manager: DatabaseManager, user_a: uuid.UUID
) -> None:
    """append_interaction stores every field and links the history."""
    history = HistoryRepository(db_manager, user_a).add()
    repo = InteractionRepository(db_manager, user_a)
    interaction = repo.append_interaction(
        history.id, "question", "response", "gpt-4o", 42
    )
    assert interaction.history_id == history.id
    assert interaction.question == "question"
    assert interaction.response == "response"
    assert interaction.model == "gpt-4o"
    assert interaction.tokens_used == 42
    fetched = repo.get(interaction.id)
    assert fetched is not None
    assert fetched.tokens_used == 42


def test_append_interaction_unknown_history_raises(
    db_manager: DatabaseManager, user_a: uuid.UUID
) -> None:
    """Appending to a non-existent history raises DatabaseError."""
    repo = InteractionRepository(db_manager, user_a)
    with pytest.raises(DatabaseError):
        repo.append_interaction(uuid.uuid4(), "q", "a", "gpt", 1)


def test_append_interaction_cross_user_history_raises(
    db_manager: DatabaseManager, user_a: uuid.UUID, user_b: uuid.UUID
) -> None:
    """Appending to another user's history raises DatabaseError."""
    history_a = HistoryRepository(db_manager, user_a).add()
    repo_b = InteractionRepository(db_manager, user_b)
    with pytest.raises(DatabaseError):
        repo_b.append_interaction(history_a.id, "q", "a", "gpt", 1)


def test_interaction_get_isolated(
    db_manager: DatabaseManager, user_a: uuid.UUID, user_b: uuid.UUID
) -> None:
    """get on interactions is isolated through the owning history."""
    history_a = HistoryRepository(db_manager, user_a).add()
    interaction = InteractionRepository(db_manager, user_a).append_interaction(
        history_a.id, "q", "a", "gpt", 1
    )
    assert InteractionRepository(db_manager, user_b).get(interaction.id) is None


@pytest.mark.slow
def test_filter_10k_records_under_500ms(
    db_manager: DatabaseManager, user_a: uuid.UUID
) -> None:
    """filter over 10k interactions stays below 500ms."""
    history = HistoryRepository(db_manager, user_a).add()
    repo = InteractionRepository(db_manager, user_a)
    with db_manager.session() as session:
        for index in range(10_000):
            session.add(
                InteractionModel(
                    history_id=history.id,
                    question=f"question number {index}",
                    response=f"response number {index}",
                    model="gpt",
                    tokens_used=index,
                )
            )
    start = time.perf_counter()
    result = repo.filter(keyword="question number 999")
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5
    assert len(result) >= 1
