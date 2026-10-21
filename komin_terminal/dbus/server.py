"""D-Bus server container wiring the daemon services onto the system bus."""

from __future__ import annotations

from komin_terminal.config import KominConfig
from komin_terminal.constants import (
    get_dbus_chat_namespace,
    get_dbus_history_namespace,
    get_dbus_object_path_chat,
    get_dbus_object_path_history,
    get_dbus_object_path_user,
    get_dbus_user_namespace,
)
from komin_terminal.daemon.database import DatabaseManager
from komin_terminal.daemon.http import HttpSession, QueryExecutor, RetryAdapter
from komin_terminal.daemon.session import UserSessionManager
from komin_terminal.dbus.bus import BusAbstraction, SystemBusBackend
from komin_terminal.dbus.interfaces import (
    Authorization,
    ChatInterface,
    HistoryInterface,
    UserInterface,
)
from komin_terminal.logger import get_logger, setup_logging

_LOGGER = get_logger("komin.dbus.server")


class KominDBusServer:
    """Publish the chat, history and user services on the system bus.

    Args:
        config: Fully validated application configuration.
        bus: Optional bus abstraction; defaults to a SystemBusBackend created
            in :meth:`start`.
    """

    def __init__(self, config: KominConfig, bus: BusAbstraction | None = None) -> None:
        """Initialize the server without touching the bus or the database."""
        self._config = config
        self._configured_bus = bus
        self._bus: BusAbstraction | None = None
        self._db: DatabaseManager | None = None
        self._started = False

    @property
    def database(self) -> DatabaseManager | None:
        """The database manager while the server is running."""
        return self._db

    def start(self) -> None:
        """Start the server and block until :meth:`stop` is called.

        Sets up logging, initializes the database, builds the three service
        interfaces, publishes their object paths, requests their bus names
        and then enters the main loop.

        Raises:
            RuntimeError: When the server was already started.
        """
        if self._started:
            raise RuntimeError("server already started")
        self._started = True
        setup_logging(self._config.logging.level, audit=self._config.logging.audit)
        bus = self._configured_bus if self._configured_bus is not None else SystemBusBackend()
        self._bus = bus
        db = DatabaseManager(self._config.database)
        db.initialize()
        self._db = db
        sessions = UserSessionManager()
        auth = Authorization(bus, sessions)
        chat = ChatInterface(
            auth=auth,
            sessions=sessions,
            db=db,
            executor_factory=self._executor_factory,
            bus=bus,
            default_model=self._config.backend.model,
        )
        history = HistoryInterface(auth=auth, sessions=sessions, db=db, bus=bus)
        user = UserInterface(auth=auth, sessions=sessions)
        bus.publish_object(get_dbus_object_path_chat(), chat)
        bus.publish_object(get_dbus_object_path_history(), history)
        bus.publish_object(get_dbus_object_path_user(), user)
        bus.request_name(get_dbus_chat_namespace())
        bus.request_name(get_dbus_history_namespace())
        bus.request_name(get_dbus_user_namespace())
        _LOGGER.info("komind D-Bus server is serving")
        bus.run_forever()

    def stop(self) -> None:
        """Stop the server; idempotent.

        Releases the main loop, disposes the database and disconnects the
        bus.
        """
        if self._db is not None:
            self._db.dispose()
            self._db = None
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None

    def _executor_factory(self) -> QueryExecutor:
        """Build a fresh QueryExecutor from the backend configuration.

        Returns:
            A new executor with its own httpx client and retry adapter.
        """
        session = HttpSession(self._config.backend)
        retry = RetryAdapter(max_retries=self._config.backend.max_retries)
        return QueryExecutor(session.create_client(), retry)
