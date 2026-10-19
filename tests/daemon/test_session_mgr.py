"""Tests for user identity generation and caching."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from komin_terminal.daemon.session import UserIdentity, UserSessionManager
from komin_terminal.exceptions import KominError
from komin_terminal.utils.environment import Environment

_MACHINE_A: str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_MACHINE_B: str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _machine_id_file(xdg_env: Path) -> Path:
    return xdg_env / "machine-id"


def test_same_uid_same_machine_id_is_deterministic(xdg_env: Path) -> None:
    manager = UserSessionManager(Environment())

    first = manager.get_user_id(1000)
    second = manager.get_user_id(1000)

    assert first == second
    assert first.version == 5


def test_different_uids_differ(xdg_env: Path) -> None:
    manager = UserSessionManager(Environment())

    assert manager.get_user_id(1000) != manager.get_user_id(1001)


def test_derivation_matches_formula(xdg_env: Path) -> None:
    _machine_id_file(xdg_env).write_text(_MACHINE_A + "\n", encoding="utf-8")
    manager = UserSessionManager(Environment())

    expected = uuid.uuid5(uuid.uuid5(uuid.NAMESPACE_DNS, _MACHINE_A), "1000")

    assert manager.get_user_id(1000) == expected


def test_different_machine_id_yields_different_user_id(xdg_env: Path) -> None:
    _machine_id_file(xdg_env).write_text(_MACHINE_A + "\n", encoding="utf-8")
    manager_a = UserSessionManager(Environment())
    user_a = manager_a.get_user_id(1000)

    _machine_id_file(xdg_env).write_text(_MACHINE_B + "\n", encoding="utf-8")
    manager_b = UserSessionManager(Environment())
    user_b = manager_b.get_user_id(1000)

    assert user_a != user_b


def test_machine_id_is_read_once_and_cached(xdg_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = UserSessionManager(Environment())
    calls = {"n": 0}
    original = Environment.get_machine_id

    def counting(self: Environment) -> str:
        calls["n"] += 1
        return original(self)

    monkeypatch.setattr(Environment, "get_machine_id", counting)

    manager.get_user_id(1000)
    manager.get_user_id(1000)
    manager.get_identity(1001)

    assert calls["n"] == 1


def test_clear_cache_forces_machine_id_reread(
    xdg_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = UserSessionManager(Environment())
    calls = {"n": 0}
    original = Environment.get_machine_id

    def counting(self: Environment) -> str:
        calls["n"] += 1
        return original(self)

    monkeypatch.setattr(Environment, "get_machine_id", counting)

    manager.get_user_id(1000)
    manager.clear_cache()
    manager.get_user_id(1000)

    assert calls["n"] == 2


def test_get_identity_cached_and_typed(xdg_env: Path) -> None:
    manager = UserSessionManager(Environment())

    identity = manager.get_identity(1000)
    again = manager.get_identity(1000)

    assert identity is again
    assert isinstance(identity, UserIdentity)
    assert identity.unix_uid == 1000
    assert identity.user_id == manager.get_user_id(1000)


def test_clear_cache_invalidates_identities(xdg_env: Path) -> None:
    manager = UserSessionManager(Environment())

    before = manager.get_identity(1000)
    manager.clear_cache()
    after = manager.get_identity(1000)

    assert before is not after
    assert before.user_id == after.user_id


def test_missing_machine_id_raises_komin_error(
    xdg_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KOMIN_MACHINE_ID_FILE", str(xdg_env / "does-not-exist"))
    manager = UserSessionManager(Environment())

    with pytest.raises(KominError):
        manager.get_user_id(1000)


def test_uid_stringification_stability(xdg_env: Path) -> None:
    _machine_id_file(xdg_env).write_text(_MACHINE_A + "\n", encoding="utf-8")
    manager = UserSessionManager(Environment())

    assert manager.get_user_id(0) == uuid.uuid5(uuid.uuid5(uuid.NAMESPACE_DNS, _MACHINE_A), "0")
