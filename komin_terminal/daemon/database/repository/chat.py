"""Chat repository."""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select

from komin_terminal.daemon.database.models import ChatModel
from komin_terminal.daemon.database.repository.base import BaseRepository


class ChatRepository(BaseRepository[ChatModel]):
    """Repository for :class:`ChatModel` records."""

    model_class = ChatModel

    def get_by_name(self, name: str) -> ChatModel | None:
        """Fetch the user's live chat with the given name.

        Args:
            name: Chat name to look up.

        Returns:
            The matching chat, or ``None`` when absent, soft-deleted or
            owned by a different user.
        """
        stmt: Select[tuple[ChatModel]] = self._base_query().where(ChatModel.name == name)
        with self._manager.session() as session:
            return session.scalar(stmt)

    def get_owner(self, chat_id: uuid.UUID) -> uuid.UUID | None:
        """Return the owner of a chat regardless of the caller's user.

        Daemon-internal authorization support only: lets the D-Bus layer
        distinguish "not found" from "belongs to another user" when a
        user-scoped lookup returns nothing.

        Args:
            chat_id: Chat identifier to look up.

        Returns:
            The owning user id of a live chat, or ``None`` when no live
            chat exists for this id.
        """
        stmt: Select[tuple[uuid.UUID]] = select(ChatModel.user_id).where(
            ChatModel.id == chat_id, ChatModel.deleted_at.is_(None)
        )
        with self._manager.session() as session:
            return session.scalar(stmt)
