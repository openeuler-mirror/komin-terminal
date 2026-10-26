"""History and interaction repositories."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import cast

from sqlalchemy import ColumnElement, Select, or_, select

from komin_terminal.daemon.database.models import HistoryModel, InteractionModel
from komin_terminal.daemon.database.repository.base import BaseRepository
from komin_terminal.exceptions import DatabaseError


class HistoryRepository(BaseRepository[HistoryModel]):
    """Repository for :class:`HistoryModel` records."""

    model_class = HistoryModel

    def list_by_chat(
        self, chat_id: uuid.UUID, *, offset: int = 0, limit: int = 50
    ) -> Sequence[HistoryModel]:
        """List the user's live history records attached to one chat.

        Args:
            chat_id: Parent chat id.
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            The matching records, newest first.
        """
        stmt = (
            self._base_query()
            .where(HistoryModel.chat_id == chat_id)
            .order_by(HistoryModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        with self._manager.session() as session:
            return list(session.scalars(stmt))


class InteractionRepository(BaseRepository[InteractionModel]):
    """Repository for :class:`InteractionModel` records.

    Interactions carry no ``user_id`` column; isolation is enforced through
    the owning history record.
    """

    model_class = InteractionModel

    def _user_scope_conditions(self) -> list[ColumnElement[bool]]:
        """Scope interactions through their owning history's user id."""
        owned_history_ids = select(HistoryModel.id).where(
            HistoryModel.user_id == self._user_id,
            HistoryModel.deleted_at.is_(None),
        )
        return [
            cast(ColumnElement[bool], InteractionModel.history_id.in_(owned_history_ids))
        ]

    def filter(
        self,
        *,
        keyword: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[InteractionModel]:
        """Filter the user's live interactions.

        Args:
            keyword: Case-insensitive substring matched against
                ``question`` and ``response``.
            since: Lower bound on ``created_at`` (UTC, inclusive).
            until: Upper bound on ``created_at`` (UTC, inclusive).
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            The matching interactions, newest first.
        """
        stmt: Select[tuple[InteractionModel]] = self._base_query()
        if keyword:
            pattern = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    InteractionModel.question.ilike(pattern),
                    InteractionModel.response.ilike(pattern),
                )
            )
        if since is not None:
            stmt = stmt.where(InteractionModel.created_at >= since)
        if until is not None:
            stmt = stmt.where(InteractionModel.created_at <= until)
        stmt = stmt.order_by(InteractionModel.created_at.desc()).offset(offset).limit(limit)
        with self._manager.session() as session:
            return list(session.scalars(stmt))

    def list_by_chat(
        self, chat_id: uuid.UUID, *, offset: int = 0, limit: int = 50
    ) -> Sequence[InteractionModel]:
        """List the user's live interactions within one chat.

        Args:
            chat_id: Parent chat id.
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            The matching interactions, newest first.
        """
        chat_history_ids = select(HistoryModel.id).where(
            HistoryModel.user_id == self._user_id,
            HistoryModel.chat_id == chat_id,
            HistoryModel.deleted_at.is_(None),
        )
        stmt = (
            self._base_query()
            .where(InteractionModel.history_id.in_(chat_history_ids))
            .order_by(InteractionModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        with self._manager.session() as session:
            return list(session.scalars(stmt))

    def get_owner_history_id(self, interaction_id: uuid.UUID) -> uuid.UUID | None:
        """Resolve the history owning an interaction, including deleted ones.

        Unlike :meth:`get`, this lookup is not scoped to live histories so
        that a soft-deleted exchange can still be restored. User isolation
        is enforced through the owning history's ``user_id``.

        Args:
            interaction_id: Interaction identifier.

        Returns:
            The owning history id when the interaction exists and belongs
            to this user, ``None`` otherwise.
        """
        stmt = (
            select(HistoryModel.id)
            .join(InteractionModel, InteractionModel.history_id == HistoryModel.id)
            .where(
                InteractionModel.id == interaction_id,
                HistoryModel.user_id == self._user_id,
            )
        )
        with self._manager.session() as session:
            return cast("uuid.UUID | None", session.scalar(stmt))

    def append_interaction(
        self,
        history_id: uuid.UUID,
        question: str,
        response: str,
        model: str,
        tokens_used: int,
    ) -> InteractionModel:
        """Append a question/answer exchange to one of the user's histories.

        Args:
            history_id: Owning history id.
            question: The user's question.
            response: The assistant's response.
            model: AI model that produced the response.
            tokens_used: Tokens consumed.

        Returns:
            The persisted interaction.

        Raises:
            DatabaseError: When the history does not exist, is soft-deleted
                or belongs to a different user.
        """
        with self._manager.session() as session:
            history = session.scalar(
                select(HistoryModel).where(
                    HistoryModel.id == history_id,
                    HistoryModel.user_id == self._user_id,
                    HistoryModel.deleted_at.is_(None),
                )
            )
            if history is None:
                raise DatabaseError(
                    f"history {history_id} not found for this user",
                    detail="append_interaction requires an existing live history owned by the user",
                )
            interaction = InteractionModel(
                history_id=history_id,
                question=question,
                response=response,
                model=model,
                tokens_used=tokens_used,
            )
            session.add(interaction)
            session.flush()
        return interaction
