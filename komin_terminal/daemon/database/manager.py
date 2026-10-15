"""Database engine and session management.

:class:`DatabaseManager` owns the SQLAlchemy engine, creates the schema on
first use and hands out transactional sessions. Every
:class:`~sqlalchemy.exc.SQLAlchemyError` raised inside a session is
converted into :class:`~komin_terminal.exceptions.DatabaseError` so that
third-party exceptions never cross the module boundary.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from komin_terminal.config import DatabaseConfig, build_connection_string
from komin_terminal.daemon.database.models import Base, SchemaVersion
from komin_terminal.exceptions import DatabaseError
from komin_terminal.logger import get_logger

_LOGGER = get_logger("komin.database")

INITIAL_SCHEMA_VERSION: int = 1


class DatabaseManager:
    """Owns the SQLAlchemy engine and provides transactional sessions.

    The manager is lazily initialized: constructing it does not touch the
    database until :meth:`initialize` is called.
    """

    def __init__(self, config: DatabaseConfig) -> None:
        """Create the manager without touching the database.

        Args:
            config: Validated database configuration.
        """
        self._config = config
        self._engine: Engine | None = None

    @property
    def is_initialized(self) -> bool:
        """Whether :meth:`initialize` has created a live engine."""
        return self._engine is not None

    def initialize(self) -> None:
        """Create the engine and all tables.

        Idempotent: calling it again while the engine is live is a no-op.
        For sqlite the connection allows cross-thread use; for
        mysql/postgresql the pool pre-pings connections. A single
        ``schema_version`` row (value ``1``) is seeded when absent.

        Raises:
            DatabaseError: When the engine or schema cannot be created.
        """
        if self._engine is not None:
            return
        url = build_connection_string(self._config)
        engine_kwargs: dict[str, Any]
        if self._config.type == "sqlite":
            engine_kwargs = {"connect_args": {"check_same_thread": False}}
        else:
            engine_kwargs = {"pool_pre_ping": True}
        try:
            engine = create_engine(url, **engine_kwargs)
            Base.metadata.create_all(bind=engine)
        except SQLAlchemyError as exc:
            raise DatabaseError(
                "failed to initialize database engine", detail=str(exc)
            ) from exc
        self._engine = engine
        self._seed_schema_version()
        _LOGGER.info("database engine initialized (type=%s)", self._config.type)

    def _seed_schema_version(self) -> None:
        """Insert the initial schema_version row when the table is empty."""
        with self.session() as session:
            existing = session.scalar(select(SchemaVersion.version).limit(1))
            if existing is None:
                session.add(SchemaVersion(version=INITIAL_SCHEMA_VERSION))

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Provide a transactional session scope.

        Commits when the body completes normally; rolls back on any
        exception. :class:`~sqlalchemy.exc.SQLAlchemyError` is converted to
        :class:`~komin_terminal.exceptions.DatabaseError`; other exceptions
        propagate unchanged after the rollback. Sessions use
        ``expire_on_commit=False`` so returned objects stay readable after
        the session closes.

        Yields:
            A live :class:`~sqlalchemy.orm.Session`.

        Raises:
            DatabaseError: When the manager is not initialized, or when the
                body/commit raises a SQLAlchemy error.
        """
        if self._engine is None:
            raise DatabaseError("database is not initialized; call initialize() first")
        db_session = Session(bind=self._engine, expire_on_commit=False)
        try:
            yield db_session
            db_session.commit()
        except SQLAlchemyError as exc:
            db_session.rollback()
            raise DatabaseError("database operation failed", detail=str(exc)) from exc
        except Exception:
            db_session.rollback()
            raise
        finally:
            db_session.close()

    def dispose(self) -> None:
        """Dispose the engine; :meth:`initialize` may be called again."""
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            _LOGGER.info("database engine disposed")
