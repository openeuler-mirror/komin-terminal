"""Tests for komin_terminal.constants."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest
from komin_terminal import constants

_DBUS_NAME_RE = re.compile(r"^com\.[A-Za-z0-9_-]+\.komin\.(chat|history|user)$")
_DBUS_PATH_RE = re.compile(r"^/com/[A-Za-z0-9_]+/komin/(chat|history|user)$")

_HOME_PREFIX = "/" + "home" + "/"
_ROOT_PREFIX = "/" + "root" + "/"
_USERS_PREFIX = "/" + "Users" + "/"
_FORBIDDEN_PREFIXES = (_HOME_PREFIX, _ROOT_PREFIX, _USERS_PREFIX)

_FHS_WHITELIST = ("/etc/komin", "/var/lib/komin/komin.db", "/etc/machine-id")


@pytest.fixture(autouse=True)
def _restore_constants_module():
    yield
    importlib.reload(constants)


def test_version_matches_package() -> None:
    import komin_terminal

    assert constants.__version__ == komin_terminal.__version__ == "1.0.0"


def test_app_identity_constants() -> None:
    assert constants.APP_NAME == "komin"
    assert constants.CLI_COMMANDS == ("km", "komin")
    assert constants.DAEMON_NAME == "komind"
    assert f"komin-terminal/{constants.__version__}" == constants.DEFAULT_USER_AGENT
    assert constants.SYSTEM_PROMPT


def test_dbus_namespaces_match_format() -> None:
    for name in (
        constants.DBUS_CHAT_NAMESPACE,
        constants.DBUS_HISTORY_NAMESPACE,
        constants.DBUS_USER_NAMESPACE,
    ):
        assert _DBUS_NAME_RE.fullmatch(name), name


def test_dbus_object_paths_match_format() -> None:
    for path in (
        constants.DBUS_OBJECT_PATH_CHAT,
        constants.DBUS_OBJECT_PATH_HISTORY,
        constants.DBUS_OBJECT_PATH_USER,
    ):
        assert _DBUS_PATH_RE.fullmatch(path), path


def test_default_vendor_is_example() -> None:
    assert constants.DBUS_VENDOR == "example"
    assert constants.DBUS_CHAT_NAMESPACE == "com.example.komin.chat"
    assert constants.DBUS_OBJECT_PATH_CHAT == "/com/example/komin/chat"


def test_vendor_env_override_on_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(constants.ENV_DBUS_VENDOR, "acme")
    importlib.reload(constants)
    assert constants.DBUS_VENDOR == "acme"
    assert constants.DBUS_CHAT_NAMESPACE == "com.acme.komin.chat"
    assert constants.DBUS_HISTORY_NAMESPACE == "com.acme.komin.history"
    assert constants.DBUS_USER_NAMESPACE == "com.acme.komin.user"


def test_object_path_hyphen_conversion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(constants.ENV_DBUS_VENDOR, "my-corp")
    importlib.reload(constants)
    assert constants.DBUS_VENDOR == "my-corp"
    assert constants.DBUS_OBJECT_PATH_CHAT == "/com/my_corp/komin/chat"
    assert constants.DBUS_OBJECT_PATH_HISTORY == "/com/my_corp/komin/history"
    assert constants.DBUS_OBJECT_PATH_USER == "/com/my_corp/komin/user"
    assert _DBUS_PATH_RE.fullmatch(constants.DBUS_OBJECT_PATH_CHAT)


@pytest.mark.parametrize(
    ("env_var", "attribute"),
    [
        ("KOMIN_SYSTEM_CONFIG_DIR", "SYSTEM_CONFIG_DIR"),
        ("KOMIN_SQLITE_PATH", "SQLITE_DEFAULT_PATH"),
        ("KOMIN_MACHINE_ID_FILE", "MACHINE_ID_PATH"),
    ],
)
def test_fhs_env_override_on_reload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, env_var: str, attribute: str
) -> None:
    override = tmp_path / "custom-location"
    monkeypatch.setenv(env_var, str(override))
    importlib.reload(constants)
    assert getattr(constants, attribute) == override


@pytest.mark.parametrize(
    ("env_var", "attribute", "default"),
    [
        ("KOMIN_SYSTEM_CONFIG_DIR", "SYSTEM_CONFIG_DIR", "/etc/komin"),
        ("KOMIN_SQLITE_PATH", "SQLITE_DEFAULT_PATH", "/var/lib/komin/komin.db"),
        ("KOMIN_MACHINE_ID_FILE", "MACHINE_ID_PATH", "/etc/machine-id"),
    ],
)
def test_fhs_defaults_without_env(
    monkeypatch: pytest.MonkeyPatch, env_var: str, attribute: str, default: str
) -> None:
    monkeypatch.delenv(env_var, raising=False)
    importlib.reload(constants)
    assert getattr(constants, attribute) == Path(default)


def test_getter_functions_read_environment_live(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    override = tmp_path / "live-override"
    monkeypatch.setenv(constants.ENV_SYSTEM_CONFIG_DIR, str(override))
    assert constants.get_system_config_dir() == override
    monkeypatch.delenv(constants.ENV_SYSTEM_CONFIG_DIR)
    assert constants.get_system_config_dir() == Path("/etc/komin")


def test_no_hardcoded_dev_paths_in_sources() -> None:
    package_root = Path(constants.__file__).resolve().parent
    offenders: list[str] = []
    for py_file in sorted(package_root.rglob("*.py")):
        for lineno, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), start=1):
            if py_file.name == "constants.py" and any(item in line for item in _FHS_WHITELIST):
                continue
            for forbidden in _FORBIDDEN_PREFIXES:
                if forbidden in line:
                    offenders.append(f"{py_file}:{lineno}: {line.strip()}")
    assert offenders == []
