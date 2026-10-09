"""Tests for komin_terminal.utils.environment."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from komin_terminal.exceptions import KominError
from komin_terminal.utils import environment as environment_module
from komin_terminal.utils.environment import Environment, get_environment

_FAKE_MACHINE_ID = "0123456789abcdef0123456789abcdef"


def test_user_dirs_with_xdg_variables_set(env: Environment, xdg_env: Path) -> None:
    home = xdg_env / "home"
    assert env.get_user_config_dir() == home / ".config" / "komin"
    assert env.get_user_data_dir() == home / ".local" / "share" / "komin"
    assert env.get_user_cache_dir() == home / ".cache" / "komin"


def test_user_dirs_without_xdg_variables(
    env: Environment, xdg_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME")
    monkeypatch.delenv("XDG_DATA_HOME")
    monkeypatch.delenv("XDG_CACHE_HOME")
    home = xdg_env / "home"
    assert env.get_user_config_dir() == home / ".config" / "komin"
    assert env.get_user_data_dir() == home / ".local" / "share" / "komin"
    assert env.get_user_cache_dir() == home / ".cache" / "komin"


def test_empty_xdg_variables_fall_back_to_home(
    env: Environment, xdg_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "")
    monkeypatch.setenv("XDG_DATA_HOME", "")
    monkeypatch.setenv("XDG_CACHE_HOME", "")
    home = xdg_env / "home"
    assert env.get_user_config_dir() == home / ".config" / "komin"
    assert env.get_user_data_dir() == home / ".local" / "share" / "komin"
    assert env.get_user_cache_dir() == home / ".cache" / "komin"


def test_system_config_dir_uses_env_override(env: Environment, xdg_env: Path) -> None:
    assert env.get_system_config_dir() == xdg_env / "etc-komin"


def test_config_file_paths(env: Environment, xdg_env: Path) -> None:
    home = xdg_env / "home"
    assert env.get_user_config_file() == home / ".config" / "komin" / "config.yaml"
    assert env.get_system_config_file() == xdg_env / "etc-komin" / "config.yaml"


def test_machine_id_normal(env: Environment) -> None:
    assert env.get_machine_id() == _FAKE_MACHINE_ID


def test_machine_id_missing(
    env: Environment, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KOMIN_MACHINE_ID_FILE", str(tmp_path / "does-not-exist"))
    with pytest.raises(KominError):
        env.get_machine_id()


def test_machine_id_empty(
    env: Environment, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty_file = tmp_path / "empty-machine-id"
    empty_file.write_text("   \n", encoding="utf-8")
    monkeypatch.setenv("KOMIN_MACHINE_ID_FILE", str(empty_file))
    with pytest.raises(KominError):
        env.get_machine_id()


def test_ensure_dir_creates_nested_path_with_mode(env: Environment, tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "c"
    result = env.ensure_dir(target)
    assert result == target
    assert target.is_dir()
    assert stat.S_IMODE(target.stat().st_mode) == 0o700


def test_ensure_dir_custom_mode(env: Environment, tmp_path: Path) -> None:
    target = tmp_path / "custom-mode"
    env.ensure_dir(target, mode=0o750)
    assert stat.S_IMODE(target.stat().st_mode) == 0o750


def test_ensure_dir_existing_directory(env: Environment, tmp_path: Path) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    env.ensure_dir(target)
    assert stat.S_IMODE(target.stat().st_mode) == 0o700


def test_get_environment_returns_singleton(monkeypatch: pytest.MonkeyPatch, xdg_env: Path) -> None:
    del xdg_env
    monkeypatch.setattr(environment_module, "_environment_singleton", None)
    first = get_environment()
    second = get_environment()
    assert first is second
    assert isinstance(first, Environment)
