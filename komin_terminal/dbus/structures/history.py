"""History structures exchanged over D-Bus."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from komin_terminal.dbus.structures.base import Structure


@dataclass(frozen=True)
class HistoryEntry(Structure):
    """One history record.

    Attributes:
        id: History identifier.
        chat_id: Parent chat identifier, or ``None`` for standalone one-shot
            question/answer records.
        created_at: Creation timestamp (UTC).
    """

    id: uuid.UUID
    chat_id: uuid.UUID | None
    created_at: datetime


@dataclass(frozen=True)
class InteractionEntry(Structure):
    """One question/answer exchange.

    Attributes:
        id: Interaction identifier.
        history_id: Parent history identifier.
        question: The user's question.
        response: The assistant's response.
        model: AI model that produced the response.
        tokens_used: Tokens consumed.
        created_at: Creation timestamp (UTC).
    """

    id: uuid.UUID
    history_id: uuid.UUID
    question: str
    response: str
    model: str
    tokens_used: int
    created_at: datetime
