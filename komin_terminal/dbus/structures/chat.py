"""Chat structure exchanged over D-Bus."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from komin_terminal.dbus.structures.base import Structure


@dataclass(frozen=True)
class ChatInfo(Structure):
    """One chat as seen by the client.

    Attributes:
        id: Chat identifier.
        user_id: Owning user identifier.
        name: Chat name.
        description: Free-form description.
        model: AI model pinned to the chat (may be empty).
        created_at: Creation timestamp (UTC).
        updated_at: Last update timestamp (UTC).
    """

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: str
    model: str
    created_at: datetime
    updated_at: datetime
