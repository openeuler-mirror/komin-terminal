"""Tests for caller authorization."""

from __future__ import annotations

import pytest
from komin_terminal.daemon.session import UserSessionManager
from komin_terminal.dbus.interfaces import Authorization
from komin_terminal.exceptions import AccessDeniedError, DBusCommunicationError
from tests.dbus.conftest import CALLER_A, CALLER_B, UID_A, UID_B
from tests.dbus.fakes import FakeBus


def test_check_access_returns_real_uid(bus: FakeBus, sessions: UserSessionManager) -> None:
    auth = Authorization(bus, sessions)
    assert auth.check_access(CALLER_A) == UID_A
    assert auth.check_access(CALLER_B) == UID_B


def test_get_caller_uid_resolves_registered_connection(
    bus: FakeBus, sessions: UserSessionManager
) -> None:
    auth = Authorization(bus, sessions)
    assert auth.get_caller_uid(CALLER_A) == UID_A


def test_claimed_user_id_matching_passes(bus: FakeBus, sessions: UserSessionManager) -> None:
    auth = Authorization(bus, sessions)
    claimed = str(sessions.get_user_id(UID_A))
    assert auth.check_access(CALLER_A, claimed_user_id=claimed) == UID_A


def test_claimed_user_id_mismatch_denied(bus: FakeBus, sessions: UserSessionManager) -> None:
    auth = Authorization(bus, sessions)
    claimed = str(sessions.get_user_id(UID_B))
    with pytest.raises(AccessDeniedError):
        auth.check_access(CALLER_A, claimed_user_id=claimed)


def test_uid_lookup_failure_maps_to_communication_error(
    bus: FakeBus, sessions: UserSessionManager
) -> None:
    auth = Authorization(bus, sessions)
    with pytest.raises(DBusCommunicationError):
        auth.check_access(":9.9-unknown")
