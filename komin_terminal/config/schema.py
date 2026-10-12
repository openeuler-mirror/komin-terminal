"""Configuration dataclasses and validation for komin-terminal.

Converts a nested mapping (as parsed from YAML) into immutable, fully typed
configuration objects. All validation failures are collected and raised
together as a single :class:`ConfigValidationError`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Set
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, urlparse

from komin_terminal.exceptions import ConfigError, ConfigValidationError
from komin_terminal.logger import get_logger

_LOGGER = get_logger("komin.config")

_CREDENTIAL_PREFIX: str = "@systemd-credential:"
_DATABASE_TYPES: tuple[str, ...] = ("sqlite", "mysql", "postgresql")
_LOG_LEVELS: tuple[str, ...] = ("debug", "info", "warning", "error")
_BACKEND_KEYS: frozenset[str] = frozenset(
    {"url", "api_key", "model", "models", "timeout", "max_retries", "extra_headers", "proxy", "tls"}
)
_DATABASE_KEYS: frozenset[str] = frozenset(
    {"type", "sqlite", "host", "port", "name", "user", "password"}
)


@dataclass(frozen=True)
class TlsConfig:
    """TLS material for backend connections; all fields optional."""

    ca_bundle: Path | None = None
    client_cert: Path | None = None
    client_key: Path | None = None


@dataclass(frozen=True)
class ProxyConfig:
    """HTTP(S) proxy settings for backend connections."""

    http: str | None = None
    https: str | None = None


@dataclass(frozen=True)
class BackendConfig:
    """AI backend (OpenAI-compatible API) connection settings."""

    url: str
    api_key: str
    model: str
    models: tuple[str, ...] = ()
    timeout: int = 120
    max_retries: int = 3
    extra_headers: Mapping[str, str] = field(default_factory=dict)
    proxy: ProxyConfig | None = None
    tls: TlsConfig | None = None

    def __repr__(self) -> str:
        """Return a developer-safe representation with ``api_key`` redacted."""
        return (
            f"BackendConfig(url={self.url!r}, api_key='***', model={self.model!r}, "
            f"models={self.models!r}, timeout={self.timeout!r}, "
            f"max_retries={self.max_retries!r}, extra_headers={self.extra_headers!r}, "
            f"proxy={self.proxy!r}, tls={self.tls!r})"
        )


@dataclass(frozen=True)
class DatabaseConfig:
    """Persistence backend settings (sqlite, mysql or postgresql)."""

    type: Literal["sqlite", "mysql", "postgresql"] = "sqlite"
    sqlite_path: Path | None = None
    host: str = "localhost"
    port: int | None = None
    name: str = "komin"
    user: str = "komin"
    password: str = ""

    def __repr__(self) -> str:
        """Return a developer-safe representation with ``password`` redacted."""
        return (
            f"DatabaseConfig(type={self.type!r}, sqlite_path={self.sqlite_path!r}, "
            f"host={self.host!r}, port={self.port!r}, name={self.name!r}, "
            f"user={self.user!r}, password='***')"
        )


@dataclass(frozen=True)
class DisplayConfig:
    """Terminal rendering preferences."""

    theme: str = "default"
    spinner: bool = True
    max_width: int = 0


@dataclass(frozen=True)
class LoggingConfig:
    """Logging behaviour settings."""

    level: Literal["debug", "info", "warning", "error"] = "info"
    audit: bool = True


@dataclass(frozen=True)
class KominConfig:
    """Fully validated, immutable application configuration."""

    backend: BackendConfig
    database: DatabaseConfig
    display: DisplayConfig
    logging: LoggingConfig


def _warn_unknown_keys(section: Mapping[str, Any], section_name: str, known: Set[str]) -> None:
    """Log a warning for every unknown key (forward compatibility).

    Args:
        section: Mapping of one configuration section.
        section_name: Dotted name used in log messages.
        known: Recognized key names for this section.
    """
    for key in section:
        if key not in known:
            _LOGGER.warning(
                "Unknown configuration key %r in section %r ignored (forward compatibility)",
                key,
                section_name,
            )


def _required_str(
    section: Mapping[str, Any], section_name: str, key: str, errors: list[str]
) -> str | None:
    """Read a mandatory non-empty string field, recording errors if invalid.

    Args:
        section: Mapping of one configuration section.
        section_name: Dotted name used in error messages.
        key: Field name inside ``section``.
        errors: Accumulator for validation failure messages.

    Returns:
        The string value, or ``None`` when missing or invalid.
    """
    if key not in section:
        errors.append(f"{section_name}.{key}: required field is missing")
        return None
    value = section[key]
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{section_name}.{key}: must be a non-empty string")
        return None
    return value


def _optional_str(
    section: Mapping[str, Any], section_name: str, key: str, errors: list[str]
) -> str | None:
    """Read an optional string field, recording an error if the type is wrong.

    Args:
        section: Mapping of one configuration section.
        section_name: Dotted name used in error messages.
        key: Field name inside ``section``.
        errors: Accumulator for validation failure messages.

    Returns:
        The string value, or ``None`` when absent or invalid.
    """
    if key not in section:
        return None
    value = section[key]
    if not isinstance(value, str):
        errors.append(f"{section_name}.{key}: must be a string")
        return None
    return value


def _optional_int(
    section: Mapping[str, Any],
    section_name: str,
    key: str,
    minimum: int,
    maximum: int,
    default: int,
    errors: list[str],
) -> int:
    """Read an optional integer field bounded by ``[minimum, maximum]``.

    Args:
        section: Mapping of one configuration section.
        section_name: Dotted name used in error messages.
        key: Field name inside ``section``.
        minimum: Inclusive lower bound.
        maximum: Inclusive upper bound.
        default: Value returned when the field is absent.
        errors: Accumulator for validation failure messages.

    Returns:
        The validated integer, or ``default`` when absent or invalid.
    """
    if key not in section:
        return default
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"{section_name}.{key}: must be an integer")
        return default
    if not minimum <= value <= maximum:
        errors.append(f"{section_name}.{key}: must be between {minimum} and {maximum}")
        return default
    return value


def _optional_bool(
    section: Mapping[str, Any], section_name: str, key: str, default: bool, errors: list[str]
) -> bool:
    """Read an optional boolean field, recording an error on type mismatch.

    Args:
        section: Mapping of one configuration section.
        section_name: Dotted name used in error messages.
        key: Field name inside ``section``.
        default: Value returned when the field is absent.
        errors: Accumulator for validation failure messages.

    Returns:
        The validated boolean, or ``default`` when absent or invalid.
    """
    if key not in section:
        return default
    value = section[key]
    if not isinstance(value, bool):
        errors.append(f"{section_name}.{key}: must be a boolean")
        return default
    return value


def _validate_backend(raw: Mapping[str, Any] | None, errors: list[str]) -> BackendConfig | None:
    """Validate the ``backend`` section.

    Args:
        raw: Raw mapping for the section, or ``None`` when absent.
        errors: Accumulator for validation failure messages.

    Returns:
        A :class:`BackendConfig`, or ``None`` when the section is unusable.
    """
    if raw is None:
        errors.append("backend: required section is missing")
        return None
    if not isinstance(raw, Mapping):
        errors.append("backend: must be a mapping")
        return None

    url = _required_str(raw, "backend", "url", errors)
    if url is not None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            errors.append("backend.url: must be an http or https URL")
    api_key = _required_str(raw, "backend", "api_key", errors)
    model = _required_str(raw, "backend", "model", errors)

    timeout = _optional_int(raw, "backend", "timeout", 1, 600, 120, errors)
    max_retries = _optional_int(raw, "backend", "max_retries", 0, 10, 3, errors)

    models: tuple[str, ...] = ()
    if "models" in raw:
        raw_models = raw["models"]
        if not isinstance(raw_models, (list, tuple)) or not all(
            isinstance(item, str) for item in raw_models
        ):
            errors.append("backend.models: must be a list of strings")
        else:
            models = tuple(raw_models)

    extra_headers: Mapping[str, str] = {}
    if "extra_headers" in raw:
        raw_headers = raw["extra_headers"]
        if not isinstance(raw_headers, Mapping) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in raw_headers.items()
        ):
            errors.append("backend.extra_headers: must be a mapping of string to string")
        else:
            extra_headers = dict(raw_headers)

    proxy = _validate_proxy(raw.get("proxy"), errors)
    tls = _validate_tls(raw.get("tls"), errors)

    _warn_unknown_keys(raw, "backend", _BACKEND_KEYS)

    if url is None or api_key is None or model is None:
        return None
    return BackendConfig(
        url=url,
        api_key=api_key,
        model=model,
        models=models,
        timeout=timeout,
        max_retries=max_retries,
        extra_headers=extra_headers,
        proxy=proxy,
        tls=tls,
    )


def _validate_proxy(raw: Any, errors: list[str]) -> ProxyConfig | None:
    """Validate the ``backend.proxy`` subsection.

    Args:
        raw: Raw mapping for the subsection, or ``None`` when absent.
        errors: Accumulator for validation failure messages.

    Returns:
        A :class:`ProxyConfig`, or ``None`` when absent or unusable.
    """
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        errors.append("backend.proxy: must be a mapping")
        return None
    http = _optional_str(raw, "backend.proxy", "http", errors)
    https = _optional_str(raw, "backend.proxy", "https", errors)
    _warn_unknown_keys(raw, "backend.proxy", {"http", "https"})
    return ProxyConfig(http=http, https=https)


def _validate_tls(raw: Any, errors: list[str]) -> TlsConfig | None:
    """Validate the ``backend.tls`` subsection.

    Args:
        raw: Raw mapping for the subsection, or ``None`` when absent.
        errors: Accumulator for validation failure messages.

    Returns:
        A :class:`TlsConfig`, or ``None`` when absent or unusable.
    """
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        errors.append("backend.tls: must be a mapping")
        return None
    fields: dict[str, Path | None] = {}
    for key in ("ca_bundle", "client_cert", "client_key"):
        value = _optional_str(raw, "backend.tls", key, errors)
        fields[key] = Path(value) if value is not None else None
    _warn_unknown_keys(raw, "backend.tls", {"ca_bundle", "client_cert", "client_key"})
    return TlsConfig(
        ca_bundle=fields["ca_bundle"],
        client_cert=fields["client_cert"],
        client_key=fields["client_key"],
    )


def _resolve_password(value: str, errors: list[str]) -> str:
    """Resolve ``@systemd-credential:<name>`` references to real passwords.

    Args:
        value: Raw password value from the configuration file.
        errors: Accumulator for validation failure messages.

    Returns:
        The plain password, or the file content (stripped) for credential
        references. On resolution failure an error is appended and the raw
        value is returned unchanged.
    """
    if not value.startswith(_CREDENTIAL_PREFIX):
        return value
    name = value[len(_CREDENTIAL_PREFIX) :]
    if not name:
        errors.append("database.password: malformed systemd credential reference (empty name)")
        return value
    credentials_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if not credentials_dir:
        errors.append(
            "database.password: systemd credential reference requires CREDENTIALS_DIRECTORY "
            "to be set"
        )
        return value
    credential_file = Path(credentials_dir) / name
    if not credential_file.is_file():
        errors.append(f"database.password: credential file not found: {credential_file}")
        return value
    try:
        return credential_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        errors.append(f"database.password: failed to read credential file: {exc}")
        return value


def _validate_database(raw: Mapping[str, Any] | None, errors: list[str]) -> DatabaseConfig:
    """Validate the ``database`` section.

    Args:
        raw: Raw mapping for the section, or ``None`` when absent.
        errors: Accumulator for validation failure messages.

    Returns:
        A :class:`DatabaseConfig`; defaults are used for an absent section.
    """
    if raw is None:
        return DatabaseConfig()
    if not isinstance(raw, Mapping):
        errors.append("database: must be a mapping")
        return DatabaseConfig()

    raw_type = raw.get("type", "sqlite")
    if raw_type not in _DATABASE_TYPES:
        errors.append("database.type: must be one of sqlite, mysql, postgresql")
        db_type: Literal["sqlite", "mysql", "postgresql"] = "sqlite"
    else:
        db_type = raw_type

    sqlite_path: Path | None = None
    sqlite_section = raw.get("sqlite")
    if db_type == "sqlite":
        if not isinstance(sqlite_section, Mapping) or "path" not in sqlite_section:
            errors.append("database.sqlite.path: required when database.type is sqlite")
        else:
            raw_path = sqlite_section["path"]
            if not isinstance(raw_path, str) or not raw_path.strip():
                errors.append("database.sqlite.path: must be a non-empty string path")
            else:
                sqlite_path = Path(raw_path)
    if isinstance(sqlite_section, Mapping):
        _warn_unknown_keys(sqlite_section, "database.sqlite", {"path"})
    elif sqlite_section is not None:
        errors.append("database.sqlite: must be a mapping")

    host = _optional_str(raw, "database", "host", errors)
    port: int | None = None
    if "port" in raw:
        raw_port = raw["port"]
        if isinstance(raw_port, bool) or not isinstance(raw_port, int):
            errors.append("database.port: must be an integer")
        elif not 1 <= raw_port <= 65535:
            errors.append("database.port: must be between 1 and 65535")
        else:
            port = raw_port
    name = _optional_str(raw, "database", "name", errors)
    user = _optional_str(raw, "database", "user", errors)

    password = ""
    if "password" in raw:
        raw_password = raw["password"]
        if not isinstance(raw_password, str):
            errors.append("database.password: must be a string")
        else:
            password = _resolve_password(raw_password, errors)

    _warn_unknown_keys(raw, "database", _DATABASE_KEYS)

    return DatabaseConfig(
        type=db_type,
        sqlite_path=sqlite_path,
        host=host if host is not None else "localhost",
        port=port,
        name=name if name is not None else "komin",
        user=user if user is not None else "komin",
        password=password,
    )


def _validate_display(raw: Mapping[str, Any] | None, errors: list[str]) -> DisplayConfig:
    """Validate the ``display`` section.

    Args:
        raw: Raw mapping for the section, or ``None`` when absent.
        errors: Accumulator for validation failure messages.

    Returns:
        A :class:`DisplayConfig`; defaults are used for an absent section.
    """
    if raw is None:
        return DisplayConfig()
    if not isinstance(raw, Mapping):
        errors.append("display: must be a mapping")
        return DisplayConfig()
    theme = _optional_str(raw, "display", "theme", errors)
    spinner = _optional_bool(raw, "display", "spinner", True, errors)
    max_width = 0
    if "max_width" in raw:
        raw_width = raw["max_width"]
        if isinstance(raw_width, bool) or not isinstance(raw_width, int):
            errors.append("display.max_width: must be an integer")
        elif raw_width < 0:
            errors.append("display.max_width: must be >= 0")
        else:
            max_width = raw_width
    _warn_unknown_keys(raw, "display", {"theme", "spinner", "max_width"})
    return DisplayConfig(
        theme=theme if theme is not None else "default",
        spinner=spinner,
        max_width=max_width,
    )


def _validate_logging(raw: Mapping[str, Any] | None, errors: list[str]) -> LoggingConfig:
    """Validate the ``logging`` section.

    Args:
        raw: Raw mapping for the section, or ``None`` when absent.
        errors: Accumulator for validation failure messages.

    Returns:
        A :class:`LoggingConfig`; defaults are used for an absent section.
    """
    if raw is None:
        return LoggingConfig()
    if not isinstance(raw, Mapping):
        errors.append("logging: must be a mapping")
        return LoggingConfig()
    raw_level = raw.get("level", "info")
    if raw_level not in _LOG_LEVELS:
        errors.append("logging.level: must be one of debug, info, warning, error")
        level: Literal["debug", "info", "warning", "error"] = "info"
    else:
        level = raw_level
    audit = _optional_bool(raw, "logging", "audit", True, errors)
    _warn_unknown_keys(raw, "logging", {"level", "audit"})
    return LoggingConfig(level=level, audit=audit)


def validate(raw: Mapping[str, Any]) -> KominConfig:
    """Convert a nested mapping into a validated :class:`KominConfig`.

    Every validation failure is collected first and then raised together as a
    single :class:`ConfigValidationError`. Unknown keys only emit a warning
    log record (forward compatibility).

    Args:
        raw: Nested configuration mapping, typically parsed from YAML and
            already merged with the built-in defaults.

    Returns:
        The immutable, fully validated configuration object.

    Raises:
        ConfigValidationError: When any validation rule fails; ``errors``
            contains every individual failure message.
    """
    errors: list[str] = []

    for key in raw:
        if key not in ("backend", "database", "display", "logging"):
            _LOGGER.warning("Unknown configuration section %r ignored (forward compatibility)", key)

    backend = _validate_backend(raw.get("backend"), errors)
    database = _validate_database(raw.get("database"), errors)
    display = _validate_display(raw.get("display"), errors)
    logging_config = _validate_logging(raw.get("logging"), errors)

    if errors:
        raise ConfigValidationError(errors)
    assert backend is not None
    return KominConfig(backend=backend, database=database, display=display, logging=logging_config)


def build_connection_string(db: DatabaseConfig) -> str:
    """Build a SQLAlchemy connection URL from a :class:`DatabaseConfig`.

    User and password components are URL-quoted so that special characters
    (``@``, ``:``, ``/`` ...) cannot corrupt the resulting URL.

    Args:
        db: Validated database configuration.

    Returns:
        ``sqlite:///<sqlite_path>`` for sqlite, or
        ``<driver>://user:pass@host[:port]/name`` for mysql/postgresql with
        the ``:port`` segment omitted when the port is unset.

    Raises:
        ConfigError: When sqlite is selected without a configured path.
    """
    if db.type == "sqlite":
        if db.sqlite_path is None:
            raise ConfigError("database.sqlite.path is required when database.type is sqlite")
        return f"sqlite:///{db.sqlite_path}"
    driver = "mysql+pymysql" if db.type == "mysql" else "postgresql+psycopg2"
    user = quote(db.user, safe="")
    password = quote(db.password, safe="")
    host_segment = f"{db.host}:{db.port}" if db.port is not None else db.host
    return f"{driver}://{user}:{password}@{host_segment}/{db.name}"
