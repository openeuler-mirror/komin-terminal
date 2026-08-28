"""Global constants for komin-terminal.

This module is the single source of truth for application names, D-Bus
namespaces, environment-variable names and FHS default paths. It is the only
source file allowed to contain FHS absolute path literals such as
``/etc/komin`` or ``/var/lib/komin``.

Every FHS default and the D-Bus vendor can be overridden through an
environment variable. The override logic lives in getter functions so that
callers can re-read the environment at any time; the module-level constants
are assigned from those getters at import time.
"""

from __future__ import annotations

import os
from pathlib import Path

from komin_terminal import __version__ as __version__

APP_NAME: str = "komin"
CLI_COMMANDS: tuple[str, ...] = ("km", "komin")
DAEMON_NAME: str = "komind"

ENV_SYSTEM_CONFIG_DIR: str = "KOMIN_SYSTEM_CONFIG_DIR"
ENV_SQLITE_PATH: str = "KOMIN_SQLITE_PATH"
ENV_MACHINE_ID_FILE: str = "KOMIN_MACHINE_ID_FILE"
ENV_DBUS_VENDOR: str = "KOMIN_DBUS_VENDOR"

SYSTEM_PROMPT: str = "You are a helpful Linux system administration assistant."
DEFAULT_USER_AGENT: str = f"komin-terminal/{__version__}"


def get_dbus_vendor() -> str:
    """Return the D-Bus vendor segment.

    The value of the ``KOMIN_DBUS_VENDOR`` environment variable wins when it
    is set and non-empty; otherwise the development default ``example`` is
    used. Release builds replace the default via ``scripts/prepare_release.py``.

    Returns:
        The vendor identifier used in D-Bus names and object paths.
    """
    vendor = os.environ.get(ENV_DBUS_VENDOR)
    if vendor:
        return vendor
    return "example"


def get_dbus_chat_namespace() -> str:
    """Return the well-known D-Bus bus name for the chat service.

    Returns:
        Bus name in the form ``com.<vendor>.komin.chat``.
    """
    return f"com.{get_dbus_vendor()}.komin.chat"


def get_dbus_history_namespace() -> str:
    """Return the well-known D-Bus bus name for the history service.

    Returns:
        Bus name in the form ``com.<vendor>.komin.history``.
    """
    return f"com.{get_dbus_vendor()}.komin.history"


def get_dbus_user_namespace() -> str:
    """Return the well-known D-Bus bus name for the user service.

    Returns:
        Bus name in the form ``com.<vendor>.komin.user``.
    """
    return f"com.{get_dbus_vendor()}.komin.user"


def _dbus_object_path(service: str) -> str:
    """Build a D-Bus object path for ``service``.

    Hyphens in the vendor are converted to underscores because D-Bus object
    paths only allow ``[A-Za-z0-9_]`` per element.

    Args:
        service: Final object path element (chat, history or user).

    Returns:
        Object path in the form ``/com/<vendor>/komin/<service>``.
    """
    vendor = get_dbus_vendor().replace("-", "_")
    return f"/com/{vendor}/komin/{service}"


def get_dbus_object_path_chat() -> str:
    """Return the D-Bus object path for the chat service.

    Returns:
        Object path such as ``/com/example/komin/chat``.
    """
    return _dbus_object_path("chat")


def get_dbus_object_path_history() -> str:
    """Return the D-Bus object path for the history service.

    Returns:
        Object path such as ``/com/example/komin/history``.
    """
    return _dbus_object_path("history")


def get_dbus_object_path_user() -> str:
    """Return the D-Bus object path for the user service.

    Returns:
        Object path such as ``/com/example/komin/user``.
    """
    return _dbus_object_path("user")


def get_system_config_dir() -> Path:
    """Return the system configuration directory.

    ``KOMIN_SYSTEM_CONFIG_DIR`` overrides the FHS default when set and
    non-empty.

    Returns:
        Directory holding system-wide komin configuration.
    """
    override = os.environ.get(ENV_SYSTEM_CONFIG_DIR)
    if override:
        return Path(override)
    return Path("/etc/komin")


def get_sqlite_default_path() -> Path:
    """Return the default SQLite database path.

    ``KOMIN_SQLITE_PATH`` overrides the FHS default when set and non-empty.

    Returns:
        Path of the SQLite database file.
    """
    override = os.environ.get(ENV_SQLITE_PATH)
    if override:
        return Path(override)
    return Path("/var/lib/komin/komin.db")


def get_machine_id_path() -> Path:
    """Return the machine-id file path.

    ``KOMIN_MACHINE_ID_FILE`` overrides the FHS default when set and
    non-empty.

    Returns:
        Path of the machine-id file.
    """
    override = os.environ.get(ENV_MACHINE_ID_FILE)
    if override:
        return Path(override)
    return Path("/etc/machine-id")


DBUS_VENDOR: str = get_dbus_vendor()
DBUS_CHAT_NAMESPACE: str = get_dbus_chat_namespace()
DBUS_HISTORY_NAMESPACE: str = get_dbus_history_namespace()
DBUS_USER_NAMESPACE: str = get_dbus_user_namespace()
DBUS_OBJECT_PATH_CHAT: str = get_dbus_object_path_chat()
DBUS_OBJECT_PATH_HISTORY: str = get_dbus_object_path_history()
DBUS_OBJECT_PATH_USER: str = get_dbus_object_path_user()

SYSTEM_CONFIG_DIR: Path = get_system_config_dir()
SQLITE_DEFAULT_PATH: Path = get_sqlite_default_path()
MACHINE_ID_PATH: Path = get_machine_id_path()
