"""XDG base-directory paths and machine identity access.

Business code must never read ``XDG_*`` environment variables directly; the
:class:`Environment` class below is the single entry point.
"""

from __future__ import annotations

import os
from pathlib import Path

from komin_terminal import constants
from komin_terminal.exceptions import KominError

_CONFIG_FILE_NAME: str = "config.yaml"


class Environment:
    """Single entry point for XDG paths and machine identity.

    All user-level directories resolve through this class so that tests can
    isolate the filesystem by manipulating environment variables alone.
    """

    def get_user_config_dir(self) -> Path:
        """Return the per-user configuration directory.

        Returns:
            ``$XDG_CONFIG_HOME/komin`` or ``~/.config/komin`` when the
            variable is unset or empty.
        """
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        return Path(base) / constants.APP_NAME

    def get_user_data_dir(self) -> Path:
        """Return the per-user data directory.

        Returns:
            ``$XDG_DATA_HOME/komin`` or ``~/.local/share/komin`` when the
            variable is unset or empty.
        """
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        return Path(base) / constants.APP_NAME

    def get_user_cache_dir(self) -> Path:
        """Return the per-user cache directory.

        Returns:
            ``$XDG_CACHE_HOME/komin`` or ``~/.cache/komin`` when the variable
            is unset or empty.
        """
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
        return Path(base) / constants.APP_NAME

    def get_system_config_dir(self) -> Path:
        """Return the system configuration directory.

        Returns:
            The constants-level default with ``KOMIN_SYSTEM_CONFIG_DIR``
            override support.
        """
        return constants.get_system_config_dir()

    def get_user_config_file(self) -> Path:
        """Return the per-user configuration file path.

        Returns:
            ``<user_config_dir>/config.yaml``.
        """
        return self.get_user_config_dir() / _CONFIG_FILE_NAME

    def get_system_config_file(self) -> Path:
        """Return the system configuration file path.

        Returns:
            ``<system_config_dir>/config.yaml``.
        """
        return self.get_system_config_dir() / _CONFIG_FILE_NAME

    def get_machine_id(self) -> str:
        """Read and return the machine identifier.

        The file location honours the ``KOMIN_MACHINE_ID_FILE`` override via
        :func:`komin_terminal.constants.get_machine_id_path`.

        Returns:
            The stripped machine-id content.

        Raises:
            KominError: If the file does not exist, cannot be read, or is
                empty after stripping.
        """
        path = constants.get_machine_id_path()
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise KominError("Failed to read machine-id file", detail=str(path)) from exc
        machine_id = raw.strip()
        if not machine_id:
            raise KominError("Machine-id file is empty", detail=str(path))
        return machine_id

    def ensure_dir(self, path: Path, mode: int = 0o700) -> Path:
        """Create ``path`` (including parents) and enforce its permissions.

        Args:
            path: Directory to create.
            mode: Permission bits to enforce via ``chmod``.

        Returns:
            The ``path`` argument, for chaining.
        """
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(mode)
        return path


_environment_singleton: Environment | None = None


def get_environment() -> Environment:
    """Return the process-level :class:`Environment` singleton.

    Returns:
        The shared ``Environment`` instance, created on first use.
    """
    global _environment_singleton
    if _environment_singleton is None:
        _environment_singleton = Environment()
    return _environment_singleton
