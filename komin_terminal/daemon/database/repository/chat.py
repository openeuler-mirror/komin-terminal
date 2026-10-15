"""Chat repository."""

from __future__ import annotations

from sqlalchemy import Select

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
