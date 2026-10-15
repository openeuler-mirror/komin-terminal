"""Tests for the generic BaseRepository CRUD, soft-delete and isolation."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from komin_terminal.daemon.database import (
    ChatRepository,
    DatabaseManager,
    HistoryRepository,
    InteractionRepository,
)

REPO_KINDS = ("chat", "history", "interaction")


def _make_repo(kind: str, manager: DatabaseManager, user_id: uuid.UUID) -> Any:
    """Instantiate a repository of the given kind for one user."""
    if kind == "chat":
        return ChatRepository(manager, user_id)
    if kind == "history":
        return HistoryRepository(manager, user_id)
    return InteractionRepository(manager, user_id)


def _add_record(kind: str, manager: DatabaseManager, user_id: uuid.UUID) -> Any:
    """Insert one record of the given kind owned by ``user_id``."""
    repo = _make_repo(kind, manager, user_id)
    if kind == "chat":
        return repo.add(name="base-chat")
    if kind == "history":
        return repo.add()
    history = _add_record("history", manager, user_id)
    return repo.add(history_id=history.id, question="base-question")


@pytest.mark.parametrize("kind", REPO_KINDS)
def test_add_get_roundtrip(
    kind: str, db_manager: DatabaseManager, user_a: uuid.UUID
) -> None:
    """add persists the record and get returns it."""
    record = _add_record(kind, db_manager, user_a)
    repo = _make_repo(kind, db_manager, user_a)
    fetched = repo.get(record.id)
    assert fetched is not None
    assert fetched.id == record.id


@pytest.mark.parametrize("kind", REPO_KINDS)
def test_add_injects_user_id(
    kind: str, db_manager: DatabaseManager, user_a: uuid.UUID
) -> None:
    """add injects user_id automatically for models that carry the column."""
    record = _add_record(kind, db_manager, user_a)
    if kind == "interaction":
        assert not hasattr(record, "user_id")
    else:
        assert record.user_id == user_a


@pytest.mark.parametrize("kind", REPO_KINDS)
def test_get_missing_returns_none(
    kind: str, db_manager: DatabaseManager, user_a: uuid.UUID
) -> None:
    """get on an unknown id returns None."""
    repo = _make_repo(kind, db_manager, user_a)
    assert repo.get(uuid.uuid4()) is None


@pytest.mark.parametrize("kind", REPO_KINDS)
def test_list_and_count(
    kind: str, db_manager: DatabaseManager, user_a: uuid.UUID
) -> None:
    """list returns visible records and count matches."""
    _add_record(kind, db_manager, user_a)
    _add_record(kind, db_manager, user_a)
    repo = _make_repo(kind, db_manager, user_a)
    assert repo.count() == 2
    assert len(repo.list()) == 2


@pytest.mark.parametrize("kind", REPO_KINDS)
def test_user_isolation(
    kind: str, db_manager: DatabaseManager, user_a: uuid.UUID, user_b: uuid.UUID
) -> None:
    """user_b cannot see any of user_a's records."""
    record = _add_record(kind, db_manager, user_a)
    repo_b = _make_repo(kind, db_manager, user_b)
    assert repo_b.get(record.id) is None
    assert repo_b.count() == 0
    assert repo_b.list() == []


@pytest.mark.parametrize("kind", REPO_KINDS)
def test_soft_delete_hides_and_restore(
    kind: str, db_manager: DatabaseManager, user_a: uuid.UUID
) -> None:
    """soft_delete hides the record; restore brings it back."""
    record = _add_record(kind, db_manager, user_a)
    repo = _make_repo(kind, db_manager, user_a)
    assert repo.soft_delete(record.id) is True
    assert repo.get(record.id) is None
    assert repo.list() == []
    assert repo.count() == 0
    assert repo.soft_delete(record.id) is False
    assert repo.restore(record.id) is True
    assert repo.get(record.id) is not None
    assert repo.count() == 1
    assert repo.restore(record.id) is False


@pytest.mark.parametrize("kind", REPO_KINDS)
def test_soft_delete_scoped_to_user(
    kind: str, db_manager: DatabaseManager, user_a: uuid.UUID, user_b: uuid.UUID
) -> None:
    """A user cannot delete or restore another user's record."""
    record = _add_record(kind, db_manager, user_a)
    repo_b = _make_repo(kind, db_manager, user_b)
    assert repo_b.soft_delete(record.id) is False
    assert repo_b.restore(record.id) is False
    assert _make_repo(kind, db_manager, user_a).get(record.id) is not None


@pytest.mark.parametrize("kind", REPO_KINDS)
def test_pagination_boundaries(
    kind: str, db_manager: DatabaseManager, user_a: uuid.UUID
) -> None:
    """offset/limit edge cases: zero offset, oversized limit, past-the-end."""
    for _ in range(3):
        _add_record(kind, db_manager, user_a)
    repo = _make_repo(kind, db_manager, user_a)
    assert len(repo.list(offset=0, limit=0)) == 0
    assert len(repo.list(offset=0, limit=1)) == 1
    assert len(repo.list(offset=1, limit=2)) == 2
    assert repo.list(offset=5, limit=2) == []
    assert len(repo.list(offset=0, limit=100)) == 3


@pytest.mark.parametrize("kind", REPO_KINDS)
def test_order_by_whitelist_rejects_invalid(
    kind: str, db_manager: DatabaseManager, user_a: uuid.UUID
) -> None:
    """An unknown order_by column raises ValueError."""
    repo = _make_repo(kind, db_manager, user_a)
    with pytest.raises(ValueError):
        repo.list(order_by="does_not_exist")


def test_order_by_valid_column_chat(db_manager: DatabaseManager, user_a: uuid.UUID) -> None:
    """Ordering by a whitelisted column other than created_at works."""
    repo = ChatRepository(db_manager, user_a)
    repo.add(name="b")
    repo.add(name="a")
    names = [record.name for record in repo.list(order_by="name")]
    assert names == ["b", "a"]
