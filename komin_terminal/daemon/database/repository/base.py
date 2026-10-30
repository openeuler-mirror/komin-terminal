"""Generic repository base with mandatory user isolation and soft-delete.

Every query produced by a repository starts from :meth:`BaseRepository._base_query`,
which always applies the ``deleted_at IS NULL`` filter and, for models that
carry a ``user_id`` column, an equality filter on the repository's user.
Subclasses must only add conditions on top of this query and must never
override it in a way that weakens the filters.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, ClassVar, Generic, TypeVar, cast

from sqlalchemy import func, select
from sqlalchemy.sql.expression import ColumnElement, Select

from komin_terminal.daemon.database.manager import DatabaseManager
from komin_terminal.daemon.database.models.base import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


class BaseRepository(Generic[ModelT]):
    """CRUD repository scoped to one user with soft-delete semantics.

    Args:
        manager: The database manager providing sessions.
        user_id: The user every query is scoped to.
    """

    model_class: ClassVar[type[BaseModel]]

    def __init__(self, manager: DatabaseManager, user_id: uuid.UUID) -> None:
        """Create a repository bound to a single user."""
        self._manager = manager
        self._user_id = user_id

    # ------------------------------------------------------------------ #
    # internal helpers
    # ------------------------------------------------------------------ #

    def _user_scope_conditions(self) -> list[ColumnElement[bool]]:
        """Return conditions enforcing user isolation.

        The default implementation filters on the model's ``user_id`` column
        when one exists; models without it (e.g. interactions) must override
        this method with an equivalent indirect isolation (never with an
        empty result).
        """
        user_id_column = getattr(self.model_class, "user_id", None)
        if user_id_column is None:
            return []
        return [cast(ColumnElement[bool], user_id_column == self._user_id)]

    def _base_query(self) -> Select[Any]:
        """Return a query filtered to live records of this user.

        Returns:
            A select statement over :attr:`model_class` with the soft-delete
            and user-isolation filters applied.
        """
        stmt = select(self.model_class).where(self.model_class.deleted_at.is_(None))
        for condition in self._user_scope_conditions():
            stmt = stmt.where(condition)
        return stmt

    def _order_column(self, order_by: str) -> Any:
        """Resolve an ``order_by`` column against the model's whitelist.

        Args:
            order_by: A column name.

        Returns:
            The instrumented column attribute.

        Raises:
            ValueError: When the name is not a column of the model.
        """
        allowed = set(self.model_class.__table__.columns.keys())
        if order_by not in allowed:
            raise ValueError(
                f"invalid order_by column {order_by!r}; "
                f"allowed columns: {', '.join(sorted(allowed))}"
            )
        return getattr(self.model_class, order_by)

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #

    def add(self, **fields: Any) -> ModelT:
        """Create and persist a record owned by this user.

        The repository's ``user_id`` is injected automatically when the model
        has a ``user_id`` column and the caller did not supply one.

        Args:
            **fields: Model attribute values.

        Returns:
            The persisted object (already flushed and committed).
        """
        if hasattr(self.model_class, "user_id") and "user_id" not in fields:
            fields["user_id"] = self._user_id
        instance = self.model_class(**fields)
        with self._manager.session() as session:
            session.add(instance)
            session.flush()
        return cast(ModelT, instance)

    def get(self, obj_id: uuid.UUID) -> ModelT | None:
        """Fetch a live record by id, scoped to this user.

        Args:
            obj_id: Primary key of the record.

        Returns:
            The record, or ``None`` when it is missing, soft-deleted or
            owned by a different user.
        """
        stmt = self._base_query().where(self.model_class.id == obj_id)
        with self._manager.session() as session:
            return cast(ModelT | None, session.scalar(stmt))

    def list(
        self, *, offset: int = 0, limit: int = 50, order_by: str = "created_at"
    ) -> Sequence[ModelT]:
        """List live records of this user, newest first by default.

        Args:
            offset: Number of records to skip.
            limit: Maximum number of records to return.
            order_by: Column name to order by (whitelisted per model).

        Returns:
            The matching records.

        Raises:
            ValueError: When ``order_by`` is not a model column.
        """
        column = self._order_column(order_by)
        stmt = self._base_query().order_by(column.desc()).offset(offset).limit(limit)
        with self._manager.session() as session:
            return list(session.scalars(stmt))

    def soft_delete(self, obj_id: uuid.UUID) -> bool:
        """Mark a live record of this user as soft-deleted.

        Args:
            obj_id: Primary key of the record.

        Returns:
            ``True`` when a record was deleted; ``False`` when no live
            record exists for this id and user.
        """
        stmt = self._base_query().where(self.model_class.id == obj_id)
        with self._manager.session() as session:
            instance = session.scalar(stmt)
            if instance is None:
                return False
            instance.deleted_at = datetime.now(UTC)
            instance.touch_updated()
            return True

    def restore(self, obj_id: uuid.UUID) -> bool:
        """Clear the soft-delete marker of a record of this user.

        Args:
            obj_id: Primary key of the record.

        Returns:
            ``True`` when a deleted record was restored; ``False`` when no
            soft-deleted record exists for this id and user.
        """
        stmt = (
            select(self.model_class)
            .where(self.model_class.id == obj_id)
            .where(self.model_class.deleted_at.is_not(None))
        )
        for condition in self._user_scope_conditions():
            stmt = stmt.where(condition)
        with self._manager.session() as session:
            instance = session.scalar(stmt)
            if instance is None:
                return False
            instance.deleted_at = None
            instance.touch_updated()
            return True

    def count(self) -> int:
        """Count live records of this user.

        Returns:
            The number of visible records.
        """
        stmt = select(func.count()).select_from(self._base_query().subquery())
        with self._manager.session() as session:
            return int(session.scalar(stmt) or 0)
