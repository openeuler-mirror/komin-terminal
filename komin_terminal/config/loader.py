"""Layered configuration loading for komin-terminal.

Merge order (highest precedence last): built-in defaults, system-level file,
user-level file, CLI overrides. Every layer is optional except the built-in
defaults.
"""

from __future__ import annotations

import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import yaml

from komin_terminal.config.defaults import DEFAULTS, merge
from komin_terminal.config.schema import KominConfig, validate
from komin_terminal.exceptions import ConfigError
from komin_terminal.logger import get_logger
from komin_terminal.utils.environment import Environment, get_environment

_LOGGER = get_logger("komin.config")

_USER_CONFIG_MODE: int = 0o600


class ConfigLoader:
    """Loads and merges configuration from every layer into one object."""

    def __init__(self, env: Environment | None = None) -> None:
        """Initialize the loader.

        Args:
            env: Environment abstraction used to resolve configuration file
                paths. Defaults to :func:`get_environment`; injectable for
                tests.
        """
        self._env = env if env is not None else get_environment()

    def load(
        self,
        cli_overrides: Mapping[str, Any] | None = None,
        *,
        user_file: Path | None = None,
        system_file: Path | None = None,
    ) -> KominConfig:
        """Load, merge and validate the configuration from every layer.

        Merge order: ``DEFAULTS`` <- system-level file <- user-level file <-
        ``cli_overrides``. A missing file is skipped with a debug record; a
        user-level file whose permissions differ from ``0600`` only emits a
        warning.

        When ``user_file`` or ``system_file`` is supplied the loader runs in
        exclusive mode: only the explicitly provided files are read (in
        system-then-user precedence order) and the environment-resolved
        default paths are ignored entirely. This backs ``komind --config``.

        Args:
            cli_overrides: Optional highest-precedence overrides, typically
                derived from command-line arguments.
            user_file: Optional explicit user-level configuration file;
                switches the loader into exclusive mode.
            system_file: Optional explicit system-level configuration file;
                switches the loader into exclusive mode.

        Returns:
            The fully merged and validated configuration object.

        Raises:
            ConfigError: When a configuration file cannot be read or contains
                invalid YAML; the message carries the file path and, when
                available, the line number.
            ConfigValidationError: When the merged configuration fails any
                validation rule.
        """
        data: Mapping[str, Any] = DEFAULTS

        candidates: list[tuple[Path, bool]]
        if user_file is not None or system_file is not None:
            candidates = []
            if system_file is not None:
                candidates.append((system_file, False))
            if user_file is not None:
                candidates.append((user_file, True))
        else:
            candidates = [
                (self._env.get_system_config_file(), False),
                (self._env.get_user_config_file(), True),
            ]

        for path, is_user_file in candidates:
            if not path.is_file():
                _LOGGER.debug("Configuration file not found, skipping: %s", path)
                continue
            if is_user_file:
                self._check_user_file_permissions(path)
            data = merge(data, self._load_yaml(path))

        if cli_overrides:
            data = merge(data, cli_overrides)

        return validate(data)

    def _check_user_file_permissions(self, path: Path) -> None:
        """Warn when the user-level configuration file is not mode 0600.

        Args:
            path: User-level configuration file to inspect.
        """
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
        except OSError as exc:
            _LOGGER.warning("Unable to stat configuration file %s: %s", path, exc)
            return
        if mode != _USER_CONFIG_MODE:
            _LOGGER.warning(
                "User configuration file %s has permissions %o, expected 0600", path, mode
            )

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        """Read and parse one YAML configuration file.

        Args:
            path: Configuration file to load.

        Returns:
            The parsed mapping; an empty mapping for an empty file.

        Raises:
            ConfigError: When the file cannot be read, is not valid YAML, or
                its root is not a mapping. The message carries the file path
                and, when available, the line number.
        """
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(
                f"Failed to read configuration file: {path}",
                detail=str(exc),
            ) from exc
        try:
            loaded = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ConfigError(
                f"Invalid YAML in configuration file {path}: {_format_yaml_error(exc)}"
            ) from exc
        if loaded is None:
            return {}
        if not isinstance(loaded, dict):
            raise ConfigError(f"Configuration file root must be a mapping: {path}")
        return cast("dict[str, Any]", loaded)


def _format_yaml_error(exc: yaml.YAMLError) -> str:
    """Format a YAML error with its line number when available.

    Args:
        exc: The YAML exception raised during parsing.

    Returns:
        A human-readable description including ``line N`` when the parser
        reported a problem location.
    """
    mark = getattr(exc, "problem_mark", None)
    if mark is not None:
        return f"line {mark.line + 1}: {exc}"
    return str(exc)
