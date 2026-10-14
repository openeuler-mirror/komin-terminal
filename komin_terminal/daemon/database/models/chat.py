"""Chat conversation container model."""

from __future__ import annotations

import uuid

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from komin_terminal.daemon.database.models.base import BaseModel


class ChatModel(BaseModel):
    """A named conversation container owned by a single user.

    Attributes:
        user_id: Owning user (mandatory isolation dimension, indexed).
        name: Chat name.
        description: Free-form description; defaults to empty.
        model: AI model pinned to this chat; defaults to empty.
    """

    __tablename__ = "chat"

    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(255), default="")
