"""D-Bus bus abstraction layer.

Every module of the D-Bus layer programs against :class:`BusAbstraction`;
only :class:`SystemBusBackend` may import ``dasbus``/``gi``, and it does so
lazily at instantiation time so that importing this module never requires
pygobject. All tests run against the in-memory ``FakeBus`` and never touch a
real system bus.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, NoReturn, Protocol

from komin_terminal.constants import get_dbus_vendor
from komin_terminal.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    BackendError,
    DatabaseError,
    DBusCommunicationError,
    KominError,
)


class RemoteDBusError(KominError):
    """A D-Bus call failed with a named error returned by the peer.

    Args:
        message: Human-readable error message from the peer.
        error_name: The D-Bus error name (e.g. ``com.example.komin.error.AccessDenied``).
    """

    def __init__(self, message: str, *, error_name: str) -> None:
        """Initialize the error."""
        super().__init__(message, detail=error_name)
        self._error_name = error_name

    @property
    def error_name(self) -> str:
        """D-Bus error name reported by the peer."""
        return self._error_name


@dataclass(frozen=True)
class MethodSpec:
    """Declarative description of one D-Bus method.

    Attributes:
        name: D-Bus member name (CamelCase).
        python_name: Method name on the implementing object; the method must
            accept the D-Bus parameters positionally plus a ``caller``
            keyword argument carrying the caller's connection name.
        in_signature: D-Bus type signature of each input parameter.
        out_signature: D-Bus type signature of the return value, or ``None``
            for methods without a reply.
    """

    name: str
    python_name: str
    in_signature: tuple[str, ...]
    out_signature: str | None


@dataclass(frozen=True)
class SignalSpec:
    """Declarative description of one D-Bus signal.

    Attributes:
        name: D-Bus signal name (CamelCase).
        signature: D-Bus type signature of each signal parameter.
    """

    name: str
    signature: tuple[str, ...]


@dataclass(frozen=True)
class InterfaceSpec:
    """Declarative description of a published D-Bus interface.

    Attributes:
        interface_name: Well-known D-Bus interface name.
        methods: Exported methods.
        signals: Exported signals.
    """

    interface_name: str
    methods: tuple[MethodSpec, ...]
    signals: tuple[SignalSpec, ...] = field(default_factory=tuple)


class BusAbstraction(Protocol):
    """Bus operations required by the daemon and the CLI client."""

    def publish_object(self, path: str, obj: object) -> None:
        """Publish ``obj`` under the object path ``path``."""
        ...

    def request_name(self, name: str) -> None:
        """Acquire the well-known bus name ``name``."""
        ...

    def get_proxy(self, name: str, path: str) -> Any:
        """Return a client proxy for the object ``path`` owned by ``name``."""
        ...

    def get_caller_uid(self, connection_name: str) -> int:
        """Resolve the Unix UID of a bus connection name."""
        ...

    def emit_signal(self, path: str, interface: str, member: str, args: tuple[Any, ...]) -> None:
        """Emit a signal from the object published at ``path``."""
        ...

    def subscribe_signal(
        self,
        path: str,
        interface: str,
        member: str,
        callback: Callable[..., None],
    ) -> None:
        """Invoke ``callback`` with the signal arguments on each match."""
        ...

    def disconnect(self) -> None:
        """Release bus resources; idempotent."""
        ...

    def run_forever(self) -> None:
        """Block on the bus main loop until :meth:`disconnect` is called.

        Production backends run the GLib main loop here so that incoming
        method calls are dispatched; in-memory fakes simply block until
        released.
        """
        ...


class SupportsDBusSpec(Protocol):
    """Objects publishable by :class:`SystemBusBackend`."""

    def get_dbus_spec(self) -> InterfaceSpec:
        """Return the declarative D-Bus specification of this object."""
        ...


def _build_introspection_xml(spec: InterfaceSpec) -> str:
    """Render the introspection XML for ``spec``.

    Args:
        spec: Declarative interface description.

    Returns:
        D-Bus introspection XML as a string.
    """
    lines = ['<?xml version="1.0"?>', "<node>"]
    lines.append(f'  <interface name="{spec.interface_name}">')
    for method in spec.methods:
        lines.append(f'    <method name="{method.name}">')
        for index, signature in enumerate(method.in_signature):
            lines.append(f'      <arg name="arg{index}" type="{signature}" direction="in"/>')
        if method.out_signature is not None:
            out_type = method.out_signature
            lines.append(f'      <arg name="result" type="{out_type}" direction="out"/>')
        lines.append("    </method>")
    for signal in spec.signals:
        lines.append(f'    <signal name="{signal.name}">')
        for index, signature in enumerate(signal.signature):
            lines.append(f'      <arg name="arg{index}" type="{signature}"/>')
        lines.append("    </signal>")
    lines.append("  </interface>")
    lines.append("</node>")
    return "\n".join(lines)


def _native_to_variant(value: Any) -> Any:
    """Wrap one Python scalar in a GLib variant for ``a{sv}`` transport.

    Args:
        value: A bool, int, float or str structure field value.

    Returns:
        The matching GLib variant.

    Raises:
        TypeError: For unsupported value types.
    """
    from gi.repository import GLib  # noqa: PLC0415 - deferred by design

    if isinstance(value, bool):
        return GLib.Variant("b", value)
    if isinstance(value, int):
        return GLib.Variant("x", value)
    if isinstance(value, float):
        return GLib.Variant("d", value)
    if isinstance(value, str):
        return GLib.Variant("s", value)
    raise TypeError(f"unsupported structure value type: {type(value).__name__}")


def _structure_to_dbus(value: Any) -> Any:
    """Convert plain structure data into the GLib variant wire shape.

    GLib builds ``a{sv}`` values from lists of ``(key, variant)`` pairs, not
    from plain dicts, so every dict returned by an interface method must be
    reshaped before dasbus serializes the reply. Nested lists are converted
    recursively; every other value passes through unchanged.

    Args:
        value: The method return value (dict, list of dicts, or scalar).

    Returns:
        The wire-shape equivalent of ``value``.
    """
    if isinstance(value, dict):
        return [(str(key), _native_to_variant(item)) for key, item in value.items()]
    if isinstance(value, (list, tuple)):
        return [_structure_to_dbus(item) for item in value]
    return value


def _make_dispatch_method(
    target: object, python_name: str, out_signature: str | None
) -> Callable[..., Any]:
    """Build one adapter method forwarding a D-Bus call to ``target``.

    The generated method accepts the D-Bus parameters positionally and the
    caller connection name through dasbus' ``call_info`` keyword argument.

    Args:
        target: The plain interface object implementing ``python_name``.
        python_name: Method name on ``target``.
        out_signature: D-Bus return signature; structure replies (``a{sv}``)
            are reshaped to the GLib wire format.

    Returns:
        The adapter method.
    """

    def method(self: Any, *args: Any, call_info: Mapping[str, Any]) -> Any:
        del self
        caller = str(call_info.get("sender", ""))
        result = getattr(target, python_name)(*args, caller=caller)
        if out_signature and "{sv}" in out_signature:
            result = _structure_to_dbus(result)
        return result

    setattr(method, "__dbus_handler_accepts_additional_arguments__", True)  # noqa: B010
    return method


def _build_adapter(target: object, spec: InterfaceSpec) -> Any:
    """Build a dasbus-publishable adapter around a plain interface object.

    Args:
        target: The plain interface object.
        spec: Its declarative D-Bus specification.

    Returns:
        An adapter instance carrying introspection XML, dispatch methods and
        signal placeholders.
    """
    from dasbus.signal import Signal  # noqa: PLC0415 - deferred by design

    members: dict[str, Any] = {"__dbus_xml__": _build_introspection_xml(spec)}
    for method_spec in spec.methods:
        members[method_spec.name] = _make_dispatch_method(
            target, method_spec.python_name, method_spec.out_signature
        )
    for signal_spec in spec.signals:
        members[signal_spec.name] = Signal()
    adapter_class = type(f"DBusAdapter_{spec.interface_name.replace('.', '_')}", (), members)
    return adapter_class()


class _KominErrorMapper:
    """Map komin exception types to D-Bus error names.

    The mapper walks the exception MRO so subclasses inherit the mapping of
    their parents. Used by the dasbus server handler when a published method
    raises.
    """

    _MAPPING: tuple[tuple[type[BaseException], str], ...] = (
        (AccessDeniedError, "AccessDenied"),
        (KeyError, "NotFound"),
        (DatabaseError, "DatabaseError"),
        (AuthenticationError, "AuthenticationError"),
        (BackendError, "BackendError"),
        (KominError, "KominError"),
    )

    def get_error_name(self, exception_type: type[BaseException]) -> str:
        """Return the D-Bus error name for an exception type.

        Args:
            exception_type: The raised exception type.

        Returns:
            Error name ``com.<vendor>.komin.error.<Suffix>``.
        """
        prefix = f"com.{get_dbus_vendor()}.komin.error"
        for klass in exception_type.__mro__:
            for mapped, suffix in self._MAPPING:
                if klass is mapped:
                    return f"{prefix}.{suffix}"
        return f"{prefix}.Error"


def _map_client_error(error: BaseException) -> NoReturn:
    """Convert an exception raised by a dasbus proxy into komin exceptions.

    Args:
        error: Exception raised during the proxy call.

    Raises:
        RemoteDBusError: For named D-Bus errors returned by the peer.
        KominError: Re-raised unchanged.
        DBusCommunicationError: For every other failure.
    """
    dbus_name = getattr(error, "dbus_name", None)
    if isinstance(dbus_name, str):
        raise RemoteDBusError(str(error), error_name=dbus_name) from error
    if isinstance(error, KominError):
        raise error
    raise DBusCommunicationError(f"D-Bus call failed: {error}") from error


def _dbus_to_native(value: Any) -> Any:
    """Recursively convert a D-Bus reply into plain Python values.

    dasbus unwraps only the outermost variant of a reply, so ``a{sv}``
    structures arrive as dicts whose values are still ``GLib.Variant``
    objects. This helper unpacks every nested variant so callers only ever
    see native types.

    Args:
        value: The reply value, possibly containing GLib variants.

    Returns:
        The fully unpacked native equivalent of ``value``.
    """
    from gi.repository import GLib  # noqa: PLC0415 - deferred by design

    if isinstance(value, GLib.Variant):
        return _dbus_to_native(value.unpack())
    if isinstance(value, dict):
        return {key: _dbus_to_native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_dbus_to_native(item) for item in value]
    return value

class _RemoteProxy:
    """Wrap a dasbus proxy so every call maps errors into komin exceptions."""

    def __init__(self, proxy: Any) -> None:
        """Wrap ``proxy``."""
        self._proxy = proxy

    def __getattr__(self, item: str) -> Any:
        """Expose proxy members with error mapping applied to calls."""
        member = getattr(self._proxy, item)
        if not callable(member):
            return member

        def call(*args: Any) -> Any:
            try:
                return _dbus_to_native(member(*args))
            except Exception as exc:  # noqa: BLE001 - boundary mapping
                _map_client_error(exc)

        return call


def _to_variant(value: Any) -> Any:
    """Convert a primitive signal argument to a GLib variant.

    Args:
        value: A ``str``, ``int`` or ``bool`` signal argument.

    Returns:
        A ``GLib.Variant`` instance.

    Raises:
        TypeError: For unsupported argument types.
    """
    from gi.repository import GLib  # noqa: PLC0415 - deferred by design

    if isinstance(value, bool):
        return GLib.Variant("b", value)
    if isinstance(value, int):
        return GLib.Variant("i", value)
    if isinstance(value, str):
        return GLib.Variant("s", value)
    raise TypeError(f"unsupported signal argument type: {type(value).__name__}")


class SystemBusBackend:
    """Production :class:`BusAbstraction` implementation wrapping dasbus.

    This is the only class allowed to import ``dasbus``/``gi``. The imports
    are deferred to instantiation so machines without pygobject can still
    import this module and run the full offline test suite.
    """

    def __init__(self) -> None:
        """Connect to the system bus.

        Raises:
            DBusCommunicationError: When the D-Bus bindings are missing or
                the system bus cannot be reached.
        """
        try:
            from dasbus.connection import SystemMessageBus  # noqa: PLC0415
        except ImportError as exc:
            raise DBusCommunicationError(
                "D-Bus bindings (dasbus/pygobject) are not available",
                detail=str(exc),
            ) from exc
        try:
            self._bus = SystemMessageBus()
        except Exception as exc:  # noqa: BLE001 - boundary mapping
            raise DBusCommunicationError(
                "cannot connect to the D-Bus system bus", detail=str(exc)
            ) from exc
        self._handlers: list[Any] = []
        self._subscriptions: list[int] = []
        self._disconnected = False
        self._loop: Any = None
        self._dispatch_loop: Any = None
        self._dispatch_thread: threading.Thread | None = None

    def run_forever(self) -> None:
        """Run the GLib main loop so bus method calls are dispatched.

        Blocks until :meth:`disconnect` quits the loop. SIGTERM and SIGINT
        are wired into the loop via ``GLib.unix_signal_add`` because Python
        signal handlers do not run while the C main loop is blocking.

        Raises:
            DBusCommunicationError: When the GLib bindings are unavailable.
        """
        try:
            from gi.repository import GLib  # noqa: PLC0415 - deferred by design
        except ImportError as exc:
            raise DBusCommunicationError(
                "GLib bindings (pygobject) are not available", detail=str(exc)
            ) from exc
        import signal  # noqa: PLC0415

        loop = GLib.MainLoop()
        self._loop = loop

        def _quit_on_signal() -> bool:
            loop.quit()
            return False

        for signum in (signal.SIGTERM, signal.SIGINT):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signum, _quit_on_signal)

        loop.run()

    def _quit_loop(self) -> None:
        """Stop the main loop started by :meth:`run_forever`; idempotent."""
        if self._loop is not None:
            self._loop.quit()
            self._loop = None

    def publish_object(self, path: str, obj: object) -> None:
        """Publish ``obj`` under ``path`` with caller injection.

        Args:
            path: D-Bus object path.
            obj: Interface object providing ``get_dbus_spec()``.

        Raises:
            ValueError: When ``obj`` does not provide a D-Bus specification.
        """
        spec_getter = getattr(obj, "get_dbus_spec", None)
        if not callable(spec_getter):
            raise ValueError("published objects must provide get_dbus_spec()")
        spec: InterfaceSpec = spec_getter()
        adapter = _build_adapter(obj, spec)
        from dasbus.server.handler import ServerObjectHandler  # noqa: PLC0415

        handler = ServerObjectHandler(
            self._bus, path, adapter, error_mapper=_KominErrorMapper()
        )
        handler.connect_object()
        self._handlers.append(handler)

    def request_name(self, name: str) -> None:
        """Acquire a well-known bus name.

        dasbus exposes name acquisition as ``register_service``; the
        abstraction keeps the ``request_name`` wording of the protocol.
        """
        self._bus.register_service(name)

    def get_proxy(self, name: str, path: str) -> Any:
        """Return an error-mapping proxy for a remote object."""
        try:
            proxy = self._bus.get_proxy(name, path)
        except Exception as exc:  # noqa: BLE001 - boundary mapping
            raise DBusCommunicationError(
                f"cannot reach D-Bus service {name}", detail=str(exc)
            ) from exc
        return _RemoteProxy(proxy)

    def get_caller_uid(self, connection_name: str) -> int:
        """Resolve the Unix UID of ``connection_name`` via the bus daemon."""
        try:
            from gi.repository import GLib  # noqa: PLC0415

            parameters = GLib.Variant("(s)", (connection_name,))
            reply = self._bus.connection.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "GetConnectionUnixUser",
                parameters,
                GLib.VariantType("(u)"),
                0,
                -1,
                None,
            )
            return int(reply.unpack()[0])
        except Exception as exc:  # noqa: BLE001 - boundary mapping
            raise DBusCommunicationError(
                f"cannot resolve UID of caller {connection_name}", detail=str(exc)
            ) from exc

    def emit_signal(self, path: str, interface: str, member: str, args: tuple[Any, ...]) -> None:
        """Emit a signal from the object published at ``path``."""
        from gi.repository import GLib  # noqa: PLC0415

        parameters = None
        if args:
            parameters = GLib.Variant.new_tuple(*(_to_variant(value) for value in args))
        self._bus.connection.emit_signal(None, path, interface, member, parameters)

    def _ensure_dispatch_loop(self) -> None:
        """Start a background GLib loop so signal callbacks are dispatched.

        GLib delivers subscribed signal callbacks only while a main loop
        iterates the connection's context. The daemon runs
        :meth:`run_forever` on its main thread; client processes (the CLI)
        have no such loop, so one is started on a daemon thread the first
        time a subscription is made. Idempotent.
        """
        if self._dispatch_thread is not None or self._loop is not None:
            return
        from gi.repository import GLib  # noqa: PLC0415 - deferred by design

        loop = GLib.MainLoop()
        self._dispatch_loop = loop
        thread = threading.Thread(
            target=loop.run, daemon=True, name="komin-dbus-dispatch"
        )
        self._dispatch_thread = thread
        thread.start()
        deadline = time.monotonic() + 2.0
        while not loop.is_running() and time.monotonic() < deadline:
            time.sleep(0.005)

    def subscribe_signal(
        self,
        path: str,
        interface: str,
        member: str,
        callback: Callable[..., None],
    ) -> None:
        """Subscribe to a signal; the callback receives the unwrapped arguments."""
        self._ensure_dispatch_loop()

        def _on_signal(
            connection: Any,
            sender_name: Any,
            object_path: Any,
            interface_name: Any,
            signal_name: Any,
            parameters: Any,
            *rest: Any,
        ) -> None:
            del connection, sender_name, object_path, interface_name, signal_name, rest
            values = parameters.unpack() if parameters is not None else ()
            callback(*values)

        subscription = self._bus.connection.signal_subscribe(
            None, interface, member, path, None, 0, _on_signal
        )
        self._subscriptions.append(int(subscription))

    def disconnect(self) -> None:
        """Quit the main loop, unsubscribe signals, unregister objects and
        disconnect (idempotent)."""
        if self._disconnected:
            return
        self._disconnected = True
        self._quit_loop()
        if self._dispatch_loop is not None:
            self._dispatch_loop.quit()
            self._dispatch_loop = None
        if self._dispatch_thread is not None:
            self._dispatch_thread.join(timeout=1.0)
            self._dispatch_thread = None
        for subscription in self._subscriptions:
            self._bus.connection.signal_unsubscribe(subscription)
        self._subscriptions.clear()
        for handler in self._handlers:
            handler.disconnect_object()
        self._handlers.clear()
        self._bus.disconnect()


__all__ = [
    "BusAbstraction",
    "InterfaceSpec",
    "MethodSpec",
    "RemoteDBusError",
    "SignalSpec",
    "SupportsDBusSpec",
    "SystemBusBackend",
]
