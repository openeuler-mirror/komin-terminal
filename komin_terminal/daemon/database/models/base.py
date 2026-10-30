"""Declarative base, abstract model foundation and schema-version marker.

Every ORM model derives from :class:`BaseModel`, which contributes a UUID
primary key, UTC timestamps and a ``deleted_at`` soft-delete marker. All
timestamps are timezone-aware UTC; local timezones are never used.

The models target the SQLAlchemy 1.4 declarative API: distribution
repositories (openEuler, RHEL) ship SQLAlchemy 1.4.x, and the RPM packages
depend on that system version rather than a bundled 2.x release.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CHAR, Column, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import Mapped, declarative_base
from sqlalchemy.sql.type_api import TypeEngine
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


class GUID(TypeDecorator[uuid.UUID]):
    """Platform-independent GUID column type.

    SQLAlchemy 1.4 has no generic UUID column type, so this decorator
    emulates one: PostgreSQL uses its native UUID type while every other
    dialect stores a 32-character hex string. Values surface as
    :class:`uuid.UUID` regardless of backend.

    Reference:
        https://gist.github.com/gmolveau/7caeeefe637679005a7bb9ae1b5e421e
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        """Pick the physical column type for ``dialect``.

        Args:
            dialect: The dialect in use.

        Returns:
            Native UUID on PostgreSQL, CHAR(32) elsewhere.
        """
        if dialect.name == "postgresql":
            return dialect.type_descriptor(UUID())
        return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        """Convert a UUID into its storage representation.

        Args:
            value: The UUID to store (or ``None``).
            dialect: The dialect in use.

        Returns:
            ``str(value)`` on PostgreSQL, a 32-char hex string elsewhere,
            or ``None``.
        """
        if value is None:
            return None
        if dialect.name == "postgresql":
            return str(value)
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(value)
        return format(value.int, "032x")

    def process_result_value(self, value: Any, dialect: Dialect) -> uuid.UUID | None:
        """Convert a stored value back into a UUID.

        Args:
            value: The stored value (or ``None``).
            dialect: The dialect in use (unused).

        Returns:
            The value as :class:`uuid.UUID`, or ``None``.
        """
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


if TYPE_CHECKING:

    class Base:
        """Typing stand-in for the runtime declarative base."""

        metadata: Any
        __table__: Any

else:
    #: Metadata base class shared by every ORM model.
    Base = declarative_base()


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

    if TYPE_CHECKING:

        def __init__(self, **kwargs: Any) -> None:
            """Type-only constructor: declarative accepts column kwargs."""

    id: Mapped[uuid.UUID] = Column(GUID(), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = Column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = Column(UTCDateTime, default=utc_now, onupdate=utc_now)
    deleted_at: Mapped[datetime | None] = Column(UTCDateTime, default=None)

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

    if TYPE_CHECKING:

        def __init__(self, **kwargs: Any) -> None:
            """Type-only constructor: declarative accepts column kwargs."""

    version: Mapped[int] = Column(Integer, primary_key=True)
