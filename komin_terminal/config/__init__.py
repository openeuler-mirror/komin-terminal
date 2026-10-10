"""Configuration management for komin-terminal.

Public surface: configuration dataclasses, the layered :class:`ConfigLoader`,
the mapping-to-dataclass :func:`validate` converter and
:func:`build_connection_string`.
"""

from komin_terminal.config.loader import ConfigLoader
from komin_terminal.config.schema import (
    BackendConfig,
    DatabaseConfig,
    DisplayConfig,
    KominConfig,
    LoggingConfig,
    ProxyConfig,
    TlsConfig,
    build_connection_string,
    validate,
)

__all__ = [
    "BackendConfig",
    "ConfigLoader",
    "DatabaseConfig",
    "DisplayConfig",
    "KominConfig",
    "LoggingConfig",
    "ProxyConfig",
    "TlsConfig",
    "build_connection_string",
    "validate",
]
