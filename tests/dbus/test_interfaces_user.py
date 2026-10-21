"""Tests for the user service interface."""

from __future__ import annotations

import uuid

from komin_terminal.daemon.session import UserSessionManager
from komin_terminal.dbus.interfaces import Authorization, UserInterface
from tests.dbus.conftest import CALLER_A, UID_A
from tests.dbus.fakes import FakeBus


def test_get_user_id_matches_session_derivation(
    bus: FakeBus, sessions: UserSessionManager
) -> None:
    interface = UserInterface(auth=Authorization(bus, sessions), sessions=sessions)
    result = interface.get_user_id(CALLER_A)
    assert result == str(sessions.get_user_id(UID_A))


def test_get_user_id_is_uuid5(bus: FakeBus, sessions: UserSessionManager) -> None:
    interface = UserInterface(auth=Authorization(bus, sessions), sessions=sessions)
    parsed = uuid.UUID(interface.get_user_id(CALLER_A))
    assert parsed.version == 5
