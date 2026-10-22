"""Theme system: semantic style names mapped to ANSI sequences.

A theme is a frozen mapping of semantic keys (``heading``, ``error``, ...)
to ANSI SGR sequences. The built-in ``default`` theme is dark-terminal
friendly; user themes live in ``<user_config_dir>/<name>.yaml`` as a flat
mapping of semantic key to a style specification written with color and
style names, e.g. ``heading: bold cyan``. Any load failure (missing file,
broken YAML, missing key, unknown token) degrades to the built-in default
with a warning and never raises.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from komin_terminal.logger import get_logger
from komin_terminal.rendering.colors import Color, Style, ansi
from komin_terminal.utils.environment import Environment, get_environment

_logger = get_logger("komin.rendering.theme")

REQUIRED_KEYS: tuple[str, ...] = (
    "heading",
    "code",
    "code_block",
    "inline_code",
    "link",
    "emphasis",
    "strong",
    "table_border",
    "info",
    "warning",
    "error",
    "notification",
    "spinner",
)
"""Semantic keys every theme must define."""

DEFAULT_STYLES: dict[str, str] = {
    "heading": ansi(Style.BOLD, Color.CYAN),
    "code": ansi(Color.GREEN),
    "code_block": ansi(Color.GREEN),
    "inline_code": ansi(Color.YELLOW),
    "link": ansi(Style.UNDERLINE, Color.BLUE),
    "emphasis": ansi(Style.ITALIC),
    "strong": ansi(Style.BOLD),
    "table_border": ansi(Style.DIM),
    "info": ansi(Color.CYAN),
    "warning": ansi(Color.YELLOW),
    "error": ansi(Color.RED),
    "notification": ansi(Color.MAGENTA),
    "spinner": ansi(Color.CYAN),
}
"""Built-in dark-terminal friendly default theme styles."""

_STYLE_TOKENS: dict[str, Style] = {member.name.lower(): member for member in Style}
_COLOR_TOKENS: dict[str, Color] = {member.name.lower(): member for member in Color}


def _default_theme() -> Theme:
    """Build the built-in default theme."""
    return Theme(name="default", styles=dict(DEFAULT_STYLES))


def _parse_style_spec(spec: str) -> str:
    """Translate a style specification like ``bold cyan`` to an ANSI sequence.

    Args:
        spec: Whitespace-separated style/color names (case-insensitive,
            ``-`` and ``_`` interchangeable).

    Returns:
        The combined SGR sequence.

    Raises:
        ValueError: If the spec is empty or contains an unknown token.
    """
    tokens = spec.split()
    if not tokens:
        raise ValueError("empty style specification")
    codes: list[Color | Style] = []
    for token in tokens:
        key = token.lower().replace("-", "_")
        style = _STYLE_TOKENS.get(key)
        if style is not None:
            codes.append(style)
            continue
        color = _COLOR_TOKENS.get(key)
        if color is not None:
            codes.append(color)
            continue
        raise ValueError(f"unknown style token: {token!r}")
    return ansi(*codes)


@dataclass(frozen=True)
class Theme:
    """Immutable collection of semantic ANSI styles.

    Attributes:
        name: Theme name (``default`` or the theme file stem).
        styles: Mapping of semantic key to ANSI SGR sequence.
    """

    name: str
    styles: Mapping[str, str]

    @classmethod
    def load(cls, name_or_path: str, env: Environment | None = None) -> Theme:
        """Load a theme by name or path, falling back to the built-in default.

        ``default`` returns the built-in theme. An absolute path is used
        verbatim; any other value is resolved to
        ``<user_config_dir>/<name>.yaml`` (appending ``.yaml`` when the
        suffix is absent). The YAML file must be a flat mapping containing
        every key in :data:`REQUIRED_KEYS`, each value being a style
        specification such as ``bold cyan``.

        Args:
            name_or_path: ``default``, a theme name, or a file path.
            env: Environment used for config-dir resolution; defaults to the
                process singleton.

        Returns:
            The loaded theme, or the built-in default when the file is
            missing, unreadable, malformed, or incomplete. Failures are
            logged as warnings and never raised.
        """
        if name_or_path == "default":
            return _default_theme()
        environment = env if env is not None else get_environment()
        candidate = Path(name_or_path)
        if not candidate.is_absolute():
            file_name = name_or_path if name_or_path.endswith(".yaml") else f"{name_or_path}.yaml"
            candidate = environment.get_user_config_dir() / file_name
        try:
            raw = candidate.read_text(encoding="utf-8")
        except OSError as exc:
            _logger.warning("Theme file %s unreadable (%s); using default theme", candidate, exc)
            return _default_theme()
        try:
            data: Any = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            _logger.warning(
                "Theme file %s is not valid YAML (%s); using default theme", candidate, exc
            )
            return _default_theme()
        if not isinstance(data, dict):
            _logger.warning("Theme file %s must contain a mapping; using default theme", candidate)
            return _default_theme()
        missing = [key for key in REQUIRED_KEYS if key not in data]
        if missing:
            _logger.warning(
                "Theme file %s misses required keys %s; using default theme", candidate, missing
            )
            return _default_theme()
        styles: dict[str, str] = {}
        for key in REQUIRED_KEYS:
            value = data[key]
            if not isinstance(value, str):
                _logger.warning(
                    "Theme %s: value for %r must be a string; using default theme", candidate, key
                )
                return _default_theme()
            try:
                styles[key] = _parse_style_spec(value)
            except ValueError as exc:
                _logger.warning(
                    "Theme %s: invalid style %r for %r (%s); using default theme",
                    candidate,
                    value,
                    key,
                    exc,
                )
                return _default_theme()
        return cls(name=candidate.stem, styles=styles)

    def get(self, key: str) -> str:
        """Return the ANSI sequence for a semantic key.

        Args:
            key: Semantic style name.

        Returns:
            The SGR sequence, or an empty string for unknown keys.
        """
        return self.styles.get(key, "")
