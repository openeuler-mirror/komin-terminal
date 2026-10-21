"""Round-trip serialization tests for the D-Bus structures."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from komin_terminal.dbus.structures import ChatInfo, HistoryEntry, InteractionEntry, Structure

EPOCH = datetime(2026, 8, 12, 10, 30, 0, tzinfo=UTC)
LATER = EPOCH + timedelta(hours=2)


def _chat_info() -> ChatInfo:
    return ChatInfo(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="ops",
        description="operations chat",
        model="glm-4",
        created_at=EPOCH,
        updated_at=LATER,
    )


def _history_entry(chat_id: uuid.UUID | None) -> HistoryEntry:
    return HistoryEntry(id=uuid.uuid4(), chat_id=chat_id, created_at=EPOCH)


def _interaction_entry() -> InteractionEntry:
    return InteractionEntry(
        id=uuid.uuid4(),
        history_id=uuid.uuid4(),
        question="how do I check load?",
        response="use uptime",
        model="glm-4",
        tokens_used=0,
        created_at=EPOCH,
    )


@pytest.mark.parametrize(
    "structure",
    [
        pytest.param(_chat_info(), id="chat-info"),
        pytest.param(_history_entry(uuid.uuid4()), id="history-with-chat"),
        pytest.param(_history_entry(None), id="history-standalone"),
        pytest.param(_interaction_entry(), id="interaction"),
    ],
)
def test_to_structure_from_structure_round_trip(structure: Structure) -> None:
    wire = structure.to_structure()
    assert type(structure).from_structure(wire) == structure


def test_uuid_and_datetime_wire_formats() -> None:
    entry = _history_entry(uuid.uuid4())
    wire = entry.to_structure()
    assert wire["id"] == str(entry.id)
    assert wire["chat_id"] == str(entry.chat_id)
    assert wire["created_at"] == EPOCH.isoformat()


def test_none_fields_survive_round_trip() -> None:
    entry = _history_entry(None)
    wire = entry.to_structure()
    assert wire["chat_id"] is None
    assert HistoryEntry.from_structure(wire).chat_id is None


def test_naive_timestamp_decoded_as_utc() -> None:
    wire = _history_entry(None).to_structure()
    wire["created_at"] = EPOCH.replace(tzinfo=None).isoformat()
    decoded = HistoryEntry.from_structure(wire)
    assert decoded.created_at == EPOCH
    assert decoded.created_at.tzinfo == UTC
