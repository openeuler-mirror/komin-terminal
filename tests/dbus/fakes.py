"""In-memory fakes for the D-Bus layer (reused by later phases).

``FakeBus`` implements :class:`BusAbstraction` entirely in memory and never
touches a real system bus; ``FakeQueryExecutor`` stands in for the HTTP
executor with a programmable event sequence.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from typing import Any

from komin_terminal.daemon.http import ChatQuery, StreamEvent
from komin_terminal.exceptions import DBusCommunicationError

_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def to_snake(name: str) -> str:
    """Convert a CamelCase D-Bus member name to snake_case.

    Args:
        name: CamelCase member name.

    Returns:
        The snake_case equivalent.
    """
    return _CAMEL_BOUNDARY.sub("_", name).lower()


def wait_until(predicate: Callable[[], bool], timeout: float = 2.0, interval: float = 0.01) -> bool:
    """Poll ``predicate`` until it is true or ``timeout`` elapses.

    Args:
        predicate: Condition polled repeatedly.
        timeout: Maximum seconds to wait.
        interval: Seconds between polls.

    Returns:
        ``True`` when the predicate became true within the timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class _FakeObjectProxy:
    """Client proxy dispatching onto a published object in memory.

    CamelCase member calls are translated to the object's snake_case methods
    with the bus' current caller injected.
    """

    def __init__(self, target: object, bus: FakeBus) -> None:
        """Bind the proxy to ``target``."""
        self._target = target
        self._bus = bus

    def __getattr__(self, name: str) -> Callable[..., Any]:
        """Return a callable for the CamelCase member ``name``."""
        method = getattr(self._target, to_snake(name))

        def call(*args: Any) -> Any:
            return method(*args, caller=self._bus.caller)

        return call


class FakeBus:
    """In-memory implementation of :class:`BusAbstraction`.

    Attributes:
        published_objects: Object path to published object.
        requested_names: Well-known names requested so far.
        emitted_signals: Every emitted signal as (path, interface, member, args).
        caller: Connection name injected into proxy dispatch.
        disconnected: Whether :meth:`disconnect` was called.
    """

    def __init__(self) -> None:
        """Initialize an empty bus."""
        self.published_objects: dict[str, object] = {}
        self.requested_names: list[str] = []
        self.emitted_signals: list[tuple[str, str, str, tuple[Any, ...]]] = []
        self.disconnected = False
        self.caller: str = ":1.100"
        self._caller_uids: dict[str, int] = {}
        self._subscriptions: dict[tuple[str, str, str], list[Callable[..., None]]] = {}
        self._proxies: dict[tuple[str, str], Any] = {}
        self._run_event = threading.Event()

    def set_caller_uid(self, connection_name: str, uid: int) -> None:
        """Register the Unix UID reported for a connection name.

        Args:
            connection_name: D-Bus connection name.
            uid: Unix UID to report for it.
        """
        self._caller_uids[connection_name] = uid

    def set_proxy(self, name: str, path: str, proxy: Any) -> None:
        """Program the proxy returned for a service name and path.

        Args:
            name: Well-known service name.
            path: Object path.
            proxy: Proxy object to return.
        """
        self._proxies[(name, path)] = proxy

    def signals(self, member: str) -> list[tuple[Any, ...]]:
        """Return the argument tuples emitted for signal ``member``.

        Args:
            member: Signal name to filter on.

        Returns:
            The matching argument tuples in emission order.
        """
        matches = (
            args for _, _, signal_member, args in self.emitted_signals
            if signal_member == member
        )
        return list(matches)

    def publish_object(self, path: str, obj: object) -> None:
        """Record the published object."""
        self.published_objects[path] = obj

    def request_name(self, name: str) -> None:
        """Record the requested well-known name."""
        self.requested_names.append(name)

    def get_proxy(self, name: str, path: str) -> Any:
        """Return a programmed proxy or one bound to the published object."""
        key = (name, path)
        if key in self._proxies:
            return self._proxies[key]
        obj = self.published_objects.get(path)
        if obj is None:
            raise DBusCommunicationError(f"no object published at {path} by {name}")
        return _FakeObjectProxy(obj, self)

    def get_caller_uid(self, connection_name: str) -> int:
        """Return the UID registered for the connection name."""
        try:
            return self._caller_uids[connection_name]
        except KeyError as exc:
            raise KeyError(f"unknown connection {connection_name}") from exc

    def emit_signal(self, path: str, interface: str, member: str, args: tuple[Any, ...]) -> None:
        """Record the signal and deliver it to matching subscribers."""
        self.emitted_signals.append((path, interface, member, args))
        for callback in self._subscriptions.get((path, interface, member), []):
            callback(*args)

    def subscribe_signal(
        self,
        path: str,
        interface: str,
        member: str,
        callback: Callable[..., None],
    ) -> None:
        """Register a callback for a signal."""
        self._subscriptions.setdefault((path, interface, member), []).append(callback)

    def run_forever(self) -> None:
        """Block until :meth:`disconnect` releases the in-memory loop."""
        self._run_event.wait()

    def disconnect(self) -> None:
        """Mark the bus as disconnected."""
        self.disconnected = True
        self._run_event.set()


class FakeQueryExecutor:
    """Programmable stand-in for :class:`QueryExecutor`.

    Attributes:
        queries: Every ChatQuery received by :meth:`ask_stream`.
        ask_queries: Every ChatQuery received by :meth:`ask`.
    """

    def __init__(
        self,
        *,
        stream_events: Sequence[StreamEvent] | None = None,
        stream_exception: Exception | None = None,
        ask_result: str = "summary",
        ask_exception: Exception | None = None,
    ) -> None:
        """Configure the fake executor.

        Args:
            stream_events: Events yielded by ask_stream; defaults to one
                chunk and a done event.
            stream_exception: Exception raised by ask_stream instead.
            ask_result: Text returned by ask.
            ask_exception: Exception raised by ask instead.
        """
        self.stream_events: list[StreamEvent] = (
            list(stream_events)
            if stream_events is not None
            else [StreamEvent(kind="chunk", content="ok"), StreamEvent(kind="done")]
        )
        self.stream_exception = stream_exception
        self.ask_result = ask_result
        self.ask_exception = ask_exception
        self.queries: list[ChatQuery] = []
        self.ask_queries: list[ChatQuery] = []

    def ask(self, query: ChatQuery) -> str:
        """Record the query and return the programmed result."""
        self.ask_queries.append(query)
        if self.ask_exception is not None:
            raise self.ask_exception
        return self.ask_result

    def ask_stream(self, query: ChatQuery) -> Iterator[StreamEvent]:
        """Record the query and yield the programmed events."""
        self.queries.append(query)
        if self.stream_exception is not None:
            raise self.stream_exception
        yield from self.stream_events
