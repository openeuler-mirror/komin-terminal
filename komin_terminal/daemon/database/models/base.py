"""Declarative base, abstract model foundation and schema-version marker.

Every ORM model derives from :class:`BaseModel`, which contributes a UUID
primary key, UTC timestamps and a ``deleted_at`` soft-delete marker. All
timestamps are timezone-aware UTC; local timezones are never used.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime.

    Returns:
        The current timestamp with ``tzinfo`` set to UTC.
    """
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """A DateTime column that always yields timezone-aware UTC values.

    SQLite does not persist timezone offsets, so naive values read back from
    the database are re-annotated as UTC. Naive values written to the
    database are interpreted as UTC as well.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        """Attach UTC tzinfo to naive values before storage.

        Args:
            value: The datetime to store, or ``None``.
            dialect: SQLAlchemy dialect in use (unused).

        Returns:
            A timezone-aware UTC datetime, or ``None``.
        """
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        """Restore UTC tzinfo on values read from the database.

        Args:
            value: The datetime read back, or ``None``.
            dialect: SQLAlchemy dialect in use (unused).

        Returns:
            A timezone-aware UTC datetime, or ``None``.
        """
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class Base(DeclarativeBase):
    """Metadata base class shared by every ORM model."""


class BaseModel(Base):
    """Abstract foundation with UUID PK, UTC timestamps and soft-delete.

    Attributes:
        id: UUID primary key generated with :func:`uuid.uuid4`.
        created_at: Creation timestamp (UTC).
        updated_at: Last modification timestamp (UTC); refreshed
            automatically on every UPDATE.
        deleted_at: Soft-delete marker; ``NULL`` means the record is live.
    """

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, onupdate=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    @property
    def is_deleted(self) -> bool:
        """Whether this record carries a soft-delete marker."""
        return self.deleted_at is not None

    def touch_updated(self) -> None:
        """Manually refresh ``updated_at`` to the current UTC time."""
        self.updated_at = utc_now()


class SchemaVersion(Base):
    """Single-row marker recording the schema version for future migrations.

    Attributes:
        version: Schema version number; the initial row holds ``1``.
    """

    __tablename__ = "schema_version"

    version: Mapped[int] = mapped_column(primary_key=True)
