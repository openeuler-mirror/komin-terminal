"""Tests for the CLI-side client proxy."""

from __future__ import annotations

from typing import Any

import pytest
from komin_terminal.constants import (
    get_dbus_chat_namespace,
    get_dbus_history_namespace,
    get_dbus_object_path_chat,
    get_dbus_object_path_history,
    get_dbus_object_path_user,
    get_dbus_user_namespace,
)
from komin_terminal.daemon.session import UserSessionManager
from komin_terminal.dbus.bus import RemoteDBusError
from komin_terminal.dbus.client import KominClient
from komin_terminal.dbus.interfaces import Authorization, UserInterface
from komin_terminal.exceptions import AccessDeniedError, DBusCommunicationError
from tests.dbus.conftest import CALLER_A, UID_A
from tests.dbus.fakes import FakeBus


class _UntouchedBus:
    """Bus double that fails the test as soon as any member is used."""

    def __getattribute__(self, name: str) -> Any:
        if name.startswith("__"):
            return object.__getattribute__(self, name)
        raise AssertionError(f"bus member {name!r} accessed during construction")


class _RecordingStub:
    """Programmable proxy stub recording calls and raising configured errors."""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.error = error

    def GetUserId(self) -> str:
        self.calls.append(("GetUserId", ()))
        if self.error is not None:
            raise self.error
        return "user-id"

    def AskQuestion(
        self, question: str, chat_id: str, attachments: list[str], model: str = ""
    ) -> str:
        self.calls.append(("AskQuestion", (question, chat_id, attachments, model)))
        if self.error is not None:
            raise self.error
        return "answer-id"


def test_construction_does_not_touch_bus() -> None:
    KominClient(bus=_UntouchedBus())  # type: ignore[arg-type]


def test_proxy_properties_are_cached() -> None:
    bus = FakeBus()
    bus.set_caller_uid(CALLER_A, UID_A)
    bus.set_proxy(get_dbus_chat_namespace(), get_dbus_object_path_chat(), _RecordingStub())
    bus.set_proxy(
        get_dbus_history_namespace(), get_dbus_object_path_history(), _RecordingStub()
    )
    bus.set_proxy(get_dbus_user_namespace(), get_dbus_object_path_user(), _RecordingStub())
    client = KominClient(bus=bus)
    assert client.chat is client.chat
    assert client.history is client.history
    assert client.user is client.user


def test_snake_case_dispatches_to_camel_case_member() -> None:
    bus = FakeBus()
    stub = _RecordingStub()
    bus.set_proxy(get_dbus_chat_namespace(), get_dbus_object_path_chat(), stub)
    client = KominClient(bus=bus)
    answer_id = client.chat.ask_question("q", "cid", ["a.txt"], "m1")
    assert answer_id == "answer-id"
    assert stub.calls == [("AskQuestion", ("q", "cid", ["a.txt"], "m1"))]


def test_is_daemon_available_true_when_user_service_answers() -> None:
    bus = FakeBus()
    bus.set_caller_uid(CALLER_A, UID_A)
    bus.caller = CALLER_A
    sessions = UserSessionManager()
    auth = Authorization(bus, sessions)
    user_service = UserInterface(auth=auth, sessions=sessions)
    bus.publish_object(get_dbus_object_path_user(), user_service)
    client = KominClient(bus=bus)
    assert client.is_daemon_available() is True


def test_is_daemon_available_false_when_unreachable() -> None:
    client = KominClient(bus=FakeBus())
    assert client.is_daemon_available() is False


def test_ensure_daemon_raises_with_troubleshooting_hint() -> None:
    client = KominClient(bus=FakeBus())
    with pytest.raises(DBusCommunicationError) as excinfo:
        client.ensure_daemon()
    assert "systemctl status komind" in excinfo.value.message


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (
            RemoteDBusError("denied", error_name="com.example.komin.error.AccessDenied"),
            AccessDeniedError,
        ),
        (RemoteDBusError("gone", error_name="com.example.komin.error.NotFound"), KeyError),
        (
            RemoteDBusError("db failed", error_name="com.example.komin.error.DatabaseError"),
            DBusCommunicationError,
        ),
        (DBusCommunicationError("bus down"), DBusCommunicationError),
        (RuntimeError("boom"), DBusCommunicationError),
    ],
)
def test_error_mapping_table(raised: Exception, expected: type[Exception]) -> None:
    bus = FakeBus()
    bus.set_proxy(get_dbus_user_namespace(), get_dbus_object_path_user(), _RecordingStub(raised))
    client = KominClient(bus=bus)
    with pytest.raises(expected):
        client.user.get_user_id()
