"""History and interaction models (question/answer records)."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from komin_terminal.daemon.database.models.base import BaseModel


class HistoryModel(BaseModel):
    """A history record, optionally attached to a chat.

    Attributes:
        user_id: Owning user (mandatory isolation dimension, indexed).
        chat_id: Optional parent chat; ``NULL`` for standalone one-shot
            question/answer records.
    """

    __tablename__ = "history"

    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    chat_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chat.id"), default=None)


class InteractionModel(BaseModel):
    """A single question/answer exchange belonging to a history record.

    This model deliberately has no ``user_id`` column; user isolation is
    enforced indirectly through the owning :class:`HistoryModel`.

    Attributes:
        history_id: Parent history record (indexed).
        question: The user's question.
        response: The assistant's response; defaults to empty.
        model: AI model that produced the response; defaults to empty.
        tokens_used: Tokens consumed; defaults to ``0``.
    """

    __tablename__ = "interaction"

    history_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("history.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    response: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(255), default="")
    tokens_used: Mapped[int] = mapped_column(default=0)
