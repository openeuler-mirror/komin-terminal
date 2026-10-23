"""Tests for komin_terminal.rendering.theme."""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path

import pytest
from komin_terminal.rendering.colors import Color, Style, ansi
from komin_terminal.rendering.theme import DEFAULT_STYLES, REQUIRED_KEYS, Theme
from komin_terminal.utils.environment import Environment

_THEME_LOGGER = "komin.rendering.theme"

_VALID_YAML = "\n".join(
    [
        "heading: bold cyan",
        "code: green",
        "code_block: green",
        "inline_code: yellow",
        "link: underline blue",
        "emphasis: italic",
        "strong: bold",
        "table_border: dim",
        "info: cyan",
        "warning: yellow",
        "error: red",
        "notification: magenta",
        "spinner: bright-cyan",
    ]
)


def _write_theme(xdg_env: Path, name: str, content: str) -> Path:
    config_dir = xdg_env / "home" / ".config" / "komin"
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / name
    path.write_text(content, encoding="utf-8")
    return path


def test_default_theme_loads() -> None:
    theme = Theme.load("default")
    assert theme.name == "default"
    assert dict(theme.styles) == DEFAULT_STYLES


def test_default_theme_has_all_required_keys() -> None:
    theme = Theme.load("default")
    for key in REQUIRED_KEYS:
        assert theme.get(key), f"missing style for {key}"


def test_custom_theme_from_user_config_dir(xdg_env: Path, env: Environment) -> None:
    _write_theme(xdg_env, "mytheme.yaml", _VALID_YAML)
    theme = Theme.load("mytheme", env=env)
    assert theme.name == "mytheme"
    assert theme.get("heading") == ansi(Style.BOLD, Color.CYAN)
    assert theme.get("spinner") == ansi(Color.BRIGHT_CYAN)
    assert theme.get("table_border") == ansi(Style.DIM)


def test_custom_theme_name_with_yaml_suffix(xdg_env: Path, env: Environment) -> None:
    _write_theme(xdg_env, "other.yaml", _VALID_YAML)
    theme = Theme.load("other.yaml", env=env)
    assert theme.name == "other"
    assert theme.get("error") == ansi(Color.RED)


def test_custom_theme_from_absolute_path(xdg_env: Path) -> None:
    path = _write_theme(xdg_env, "abs.yaml", _VALID_YAML)
    theme = Theme.load(str(path))
    assert theme.name == "abs"
    assert theme.get("info") == ansi(Color.CYAN)


def test_missing_file_falls_back_to_default(
    xdg_env: Path, env: Environment, caplog: pytest.LogCaptureFixture
) -> None:
    del xdg_env
    with caplog.at_level(logging.WARNING, logger=_THEME_LOGGER):
        theme = Theme.load("nope", env=env)
    assert theme.name == "default"
    assert dict(theme.styles) == DEFAULT_STYLES
    assert any("default theme" in record.message for record in caplog.records)


def test_corrupt_yaml_falls_back_to_default(
    xdg_env: Path, env: Environment, caplog: pytest.LogCaptureFixture
) -> None:
    _write_theme(xdg_env, "broken.yaml", "heading: [unclosed\n  bad:: {{{")
    with caplog.at_level(logging.WARNING, logger=_THEME_LOGGER):
        theme = Theme.load("broken", env=env)
    assert theme.name == "default"
    assert any("not valid YAML" in record.message for record in caplog.records)


def test_non_mapping_yaml_falls_back_to_default(
    xdg_env: Path, env: Environment, caplog: pytest.LogCaptureFixture
) -> None:
    _write_theme(xdg_env, "list.yaml", "- a\n- b\n")
    with caplog.at_level(logging.WARNING, logger=_THEME_LOGGER):
        theme = Theme.load("list", env=env)
    assert theme.name == "default"
    assert any("must contain a mapping" in record.message for record in caplog.records)


def test_missing_key_falls_back_wholly_to_default(
    xdg_env: Path, env: Environment, caplog: pytest.LogCaptureFixture
) -> None:
    lines = [line for line in _VALID_YAML.split("\n") if not line.startswith("heading")]
    _write_theme(xdg_env, "incomplete.yaml", "\n".join(lines))
    with caplog.at_level(logging.WARNING, logger=_THEME_LOGGER):
        theme = Theme.load("incomplete", env=env)
    assert theme.name == "default"
    assert dict(theme.styles) == DEFAULT_STYLES
    assert any("misses required keys" in record.message for record in caplog.records)


def test_unknown_style_token_falls_back_to_default(
    xdg_env: Path, env: Environment, caplog: pytest.LogCaptureFixture
) -> None:
    _write_theme(xdg_env, "badtoken.yaml", _VALID_YAML.replace("bold cyan", "bold sparkly"))
    with caplog.at_level(logging.WARNING, logger=_THEME_LOGGER):
        theme = Theme.load("badtoken", env=env)
    assert theme.name == "default"
    assert any("invalid style" in record.message for record in caplog.records)


def test_non_string_value_falls_back_to_default(
    xdg_env: Path, env: Environment, caplog: pytest.LogCaptureFixture
) -> None:
    _write_theme(xdg_env, "badtype.yaml", _VALID_YAML.replace("bold cyan", "123"))
    with caplog.at_level(logging.WARNING, logger=_THEME_LOGGER):
        theme = Theme.load("badtype", env=env)
    assert theme.name == "default"
    assert any("must be a string" in record.message for record in caplog.records)


def test_get_unknown_key_returns_empty_string() -> None:
    theme = Theme.load("default")
    assert theme.get("does-not-exist") == ""


def test_theme_is_frozen() -> None:
    theme = Theme.load("default")
    with pytest.raises(dataclasses.FrozenInstanceError):
        theme.name = "other"  # type: ignore[misc]
