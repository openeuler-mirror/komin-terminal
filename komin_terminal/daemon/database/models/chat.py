"""Chat conversation container model."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, String, Text
from sqlalchemy.orm import Mapped

from komin_terminal.daemon.database.models.base import GUID, BaseModel


class ChatModel(BaseModel):
    """A named conversation container owned by a single user.

    Attributes:
        user_id: Owning user (mandatory isolation dimension, indexed).
        name: Chat name.
        description: Free-form description; defaults to empty.
        model: AI model pinned to this chat; defaults to empty.
    """

    __tablename__ = "chat"

    user_id: Mapped[uuid.UUID] = Column(GUID(), index=True)
    name: Mapped[str] = Column(String(255))
    description: Mapped[str] = Column(Text, default="")
    model: Mapped[str] = Column(String(255), default="")
