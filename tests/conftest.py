"""Global test fixtures for fully offline, filesystem-isolated tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from komin_terminal.utils.environment import Environment

_FAKE_MACHINE_ID: str = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def xdg_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide complete filesystem isolation for tests touching paths.

    Redirects ``HOME``, the three ``XDG_*`` variables, the komin system
    config dir and the machine-id file into ``tmp_path``. Every test that
    touches the filesystem must use this fixture.

    Args:
        tmp_path: Per-test temporary directory provided by pytest.
        monkeypatch: Pytest fixture for environment manipulation.

    Returns:
        The ``tmp_path`` root used for isolation.
    """
    home = tmp_path / "home"
    config_home = home / ".config"
    data_home = home / ".local" / "share"
    cache_home = home / ".cache"
    for directory in (home, config_home, data_home, cache_home):
        directory.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))

    system_config_dir = tmp_path / "etc-komin"
    system_config_dir.mkdir()
    monkeypatch.setenv("KOMIN_SYSTEM_CONFIG_DIR", str(system_config_dir))

    machine_id_file = tmp_path / "machine-id"
    machine_id_file.write_text(_FAKE_MACHINE_ID + "\n", encoding="utf-8")
    monkeypatch.setenv("KOMIN_MACHINE_ID_FILE", str(machine_id_file))

    monkeypatch.delenv("KOMIN_SQLITE_PATH", raising=False)
    monkeypatch.delenv("KOMIN_DBUS_VENDOR", raising=False)
    return tmp_path


@pytest.fixture
def env(xdg_env: Path) -> Environment:
    """Return a fresh Environment instance to avoid singleton cross-talk.

    Args:
        xdg_env: Filesystem isolation fixture root.

    Returns:
        A newly constructed ``Environment``.
    """
    del xdg_env
    return Environment()
