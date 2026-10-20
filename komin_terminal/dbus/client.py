"""CLI-side D-Bus client proxy."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, NoReturn

from komin_terminal.constants import (
    get_dbus_chat_namespace,
    get_dbus_history_namespace,
    get_dbus_object_path_chat,
    get_dbus_object_path_history,
    get_dbus_object_path_user,
    get_dbus_user_namespace,
)
from komin_terminal.dbus.bus import BusAbstraction, RemoteDBusError, SystemBusBackend
from komin_terminal.exceptions import AccessDeniedError, DBusCommunicationError, KominError

_ERROR_SUFFIX_ACCESS_DENIED: str = "AccessDenied"
_ERROR_SUFFIX_NOT_FOUND: str = "NotFound"


def _to_camel(name: str) -> str:
    """Convert a snake_case method name to its D-Bus CamelCase member name.

    Args:
        name: Python-style method name.

    Returns:
        The CamelCase D-Bus member name.
    """
    return "".join(part.capitalize() for part in name.split("_"))


def _map_remote_error(error: BaseException) -> NoReturn:
    """Map an exception from a proxy call onto the komin exception hierarchy.

    Args:
        error: Exception raised by the underlying bus proxy.

    Raises:
        AccessDeniedError: For peer errors named ``...AccessDenied``.
        KeyError: For peer errors named ``...NotFound``.
        DBusCommunicationError: For every other remote or transport failure.
    """
    if isinstance(error, RemoteDBusError):
        suffix = error.error_name.rsplit(".", 1)[-1]
        if suffix == _ERROR_SUFFIX_ACCESS_DENIED:
            raise AccessDeniedError(error.message) from error
        if suffix == _ERROR_SUFFIX_NOT_FOUND:
            raise KeyError(error.message) from error
        raise DBusCommunicationError(
            f"D-Bus call failed: {error.message}", detail=error.error_name
        ) from error
    if isinstance(error, KominError):
        raise error
    raise DBusCommunicationError(f"D-Bus call failed: {error}") from error


class _NamespaceProxy:
    """Proxy for one D-Bus service namespace.

    Attribute access in snake_case is translated to CamelCase D-Bus member
    calls; every call maps peer errors onto the komin exception hierarchy.
    """

    def __init__(self, proxy: Any) -> None:
        """Wrap the raw bus proxy."""
        self._proxy = proxy

    def __getattr__(self, name: str) -> Callable[..., Any]:
        """Return a callable for the snake_case member ``name``."""
        if name.startswith("_"):
            raise AttributeError(name)
        member = getattr(self._proxy, _to_camel(name))

        def call(*args: Any) -> Any:
            try:
                return member(*args)
            except Exception as exc:  # noqa: BLE001 - boundary mapping
                _map_remote_error(exc)

        return call


class KominClient:
    """Client proxy used by the CLI to talk to the komind daemon.

    Initialization is lazy: constructing the client never touches the bus,
    keeping CLI startup within its budget. The bus connection and every
    namespace proxy are created on first use and cached.

    Args:
        bus: Optional bus abstraction; defaults to a lazy SystemBusBackend.
    """

    def __init__(self, bus: BusAbstraction | None = None) -> None:
        """Initialize the client without connecting to the bus."""
        self._configured_bus = bus
        self._active_bus: BusAbstraction | None = None
        self._chat_proxy: _NamespaceProxy | None = None
        self._history_proxy: _NamespaceProxy | None = None
        self._user_proxy: _NamespaceProxy | None = None

    @property
    def bus(self) -> BusAbstraction:
        """The bus abstraction, connected lazily on first access."""
        if self._active_bus is None:
            if self._configured_bus is not None:
                self._active_bus = self._configured_bus
            else:
                self._active_bus = SystemBusBackend()
        return self._active_bus

    @property
    def chat(self) -> _NamespaceProxy:
        """Cached proxy of the chat service."""
        if self._chat_proxy is None:
            proxy = self.bus.get_proxy(get_dbus_chat_namespace(), get_dbus_object_path_chat())
            self._chat_proxy = _NamespaceProxy(proxy)
        return self._chat_proxy

    @property
    def history(self) -> _NamespaceProxy:
        """Cached proxy of the history service."""
        if self._history_proxy is None:
            proxy = self.bus.get_proxy(
                get_dbus_history_namespace(), get_dbus_object_path_history()
            )
            self._history_proxy = _NamespaceProxy(proxy)
        return self._history_proxy

    @property
    def user(self) -> _NamespaceProxy:
        """Cached proxy of the user service."""
        if self._user_proxy is None:
            proxy = self.bus.get_proxy(get_dbus_user_namespace(), get_dbus_object_path_user())
            self._user_proxy = _NamespaceProxy(proxy)
        return self._user_proxy

    def is_daemon_available(self) -> bool:
        """Check whether the daemon answers on the system bus.

        Returns:
            ``True`` when a round trip to the user service succeeds.
        """
        try:
            self.user.get_user_id()
        except DBusCommunicationError:
            return False
        except AccessDeniedError:
            return True
        return True

    def ensure_daemon(self) -> None:
        """Verify daemon reachability before running a command.

        Raises:
            DBusCommunicationError: When the daemon is unreachable; the
                message points at ``systemctl status komind``.
        """
        if not self.is_daemon_available():
            raise DBusCommunicationError(
                "komind is not reachable on the system bus; "
                "check 'systemctl status komind'"
            )

    def subscribe_signal(
        self,
        path: str,
        interface: str,
        member: str,
        callback: Callable[..., None],
    ) -> None:
        """Subscribe to a daemon signal (e.g. the chat streaming signals).

        Args:
            path: Object path emitting the signal.
            interface: Interface name emitting the signal.
            member: Signal name.
            callback: Invoked with the signal arguments.
        """
        self.bus.subscribe_signal(path, interface, member, callback)

    def disconnect(self) -> None:
        """Disconnect from the bus; safe to call when never connected."""
        if self._active_bus is not None:
            self._active_bus.disconnect()
