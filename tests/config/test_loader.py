"""Tests for komin_terminal.config.loader."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml
from komin_terminal.config.loader import ConfigLoader
from komin_terminal.exceptions import ConfigError, ConfigValidationError
from komin_terminal.utils.benchmark import Timer
from komin_terminal.utils.environment import Environment

_SYSTEM_MODEL = "sys-model"
_USER_MODEL = "user-model"
_CLI_MODEL = "cli-model"


def _full_required(model: str) -> dict[str, Any]:
    return {
        "backend": {
            "url": "https://api.openai.com/v1",
            "api_key": "sk-test",
            "model": model,
        },
        "database": {
            "type": "sqlite",
            "sqlite": {"path": "/var/lib/komin/komin.db"},
        },
    }


def _write_yaml(path: Path, data: Mapping[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(dict(data)), encoding="utf-8")
    path.chmod(mode)


@pytest.mark.parametrize(
    ("has_system", "has_user", "has_cli", "expected_model"),
    [
        (True, False, False, _SYSTEM_MODEL),
        (False, True, False, _USER_MODEL),
        (True, True, False, _USER_MODEL),
        (True, False, True, _CLI_MODEL),
        (False, True, True, _CLI_MODEL),
        (True, True, True, _CLI_MODEL),
    ],
    ids=[
        "system-only",
        "user-only",
        "user-over-system",
        "cli-over-system",
        "cli-over-user",
        "cli-over-user-over-system",
    ],
)
def test_layer_precedence(
    xdg_env: Path,
    env: Environment,
    has_system: bool,
    has_user: bool,
    has_cli: bool,
    expected_model: str,
) -> None:
    del xdg_env
    if has_system:
        _write_yaml(env.get_system_config_file(), _full_required(_SYSTEM_MODEL))
    if has_user:
        user_data: dict[str, Any] = (
            _full_required(_USER_MODEL) if not has_system else {"backend": {"model": _USER_MODEL}}
        )
        _write_yaml(env.get_user_config_file(), user_data)
    cli_overrides: dict[str, Any] | None = {"backend": {"model": _CLI_MODEL}} if has_cli else None

    config = ConfigLoader(env=env).load(cli_overrides)
    assert config.backend.model == expected_model
    assert config.backend.url == "https://api.openai.com/v1"
    assert config.database.sqlite_path == Path("/var/lib/komin/komin.db")


def test_defaults_are_merged_in(xdg_env: Path, env: Environment) -> None:
    del xdg_env
    _write_yaml(env.get_user_config_file(), _full_required("m"))
    config = ConfigLoader(env=env).load()
    assert config.backend.timeout == 120
    assert config.backend.max_retries == 3
    assert config.display.theme == "default"
    assert config.logging.level == "info"


def test_missing_files_skipped_with_debug_log(
    xdg_env: Path, env: Environment, caplog: pytest.LogCaptureFixture
) -> None:
    del xdg_env
    with caplog.at_level(logging.DEBUG, logger="komin.config"):
        config = ConfigLoader(env=env).load(_full_required(_CLI_MODEL))
    assert config.backend.model == _CLI_MODEL
    debug_messages = [
        record.getMessage() for record in caplog.records if record.levelno == logging.DEBUG
    ]
    assert sum("not found" in message for message in debug_messages) == 2


@pytest.mark.parametrize("layer", ["system", "user"])
def test_yaml_syntax_error_raises_config_error_with_location(
    xdg_env: Path, env: Environment, layer: str
) -> None:
    del xdg_env
    path = env.get_system_config_file() if layer == "system" else env.get_user_config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('backend:\n  url: "unclosed\n', encoding="utf-8")
    with pytest.raises(ConfigError) as excinfo:
        ConfigLoader(env=env).load()
    message = excinfo.value.message
    assert str(path) in message
    assert "line" in message


@pytest.mark.parametrize("layer", ["system", "user"])
def test_yaml_root_not_mapping_raises_config_error(
    xdg_env: Path, env: Environment, layer: str
) -> None:
    del xdg_env
    path = env.get_system_config_file() if layer == "system" else env.get_user_config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ConfigError) as excinfo:
        ConfigLoader(env=env).load()
    assert "root must be a mapping" in excinfo.value.message


def test_empty_yaml_file_is_treated_as_empty(xdg_env: Path, env: Environment) -> None:
    del xdg_env
    _write_yaml(env.get_system_config_file(), _full_required(_SYSTEM_MODEL))
    user_file = env.get_user_config_file()
    user_file.parent.mkdir(parents=True, exist_ok=True)
    user_file.write_text("", encoding="utf-8")
    user_file.chmod(0o600)
    config = ConfigLoader(env=env).load()
    assert config.backend.model == _SYSTEM_MODEL


def test_user_file_permissions_not_0600_warns(
    xdg_env: Path, env: Environment, caplog: pytest.LogCaptureFixture
) -> None:
    del xdg_env
    _write_yaml(env.get_user_config_file(), _full_required(_USER_MODEL), mode=0o644)
    with caplog.at_level(logging.WARNING, logger="komin.config"):
        config = ConfigLoader(env=env).load()
    assert config.backend.model == _USER_MODEL
    assert any(
        "permissions" in record.getMessage() and "644" in record.getMessage()
        for record in caplog.records
    )


def test_user_file_permissions_0600_no_warning(
    xdg_env: Path, env: Environment, caplog: pytest.LogCaptureFixture
) -> None:
    del xdg_env
    _write_yaml(env.get_user_config_file(), _full_required(_USER_MODEL), mode=0o600)
    with caplog.at_level(logging.WARNING, logger="komin.config"):
        ConfigLoader(env=env).load()
    assert not any("permissions" in record.getMessage() for record in caplog.records)


def test_cli_overrides_without_any_files(xdg_env: Path, env: Environment) -> None:
    del xdg_env
    config = ConfigLoader(env=env).load(
        {
            "backend": {"url": "https://api.example.com", "api_key": "sk-cli", "model": "cli"},
            "database": {"type": "sqlite", "sqlite": {"path": "/var/lib/komin/cli.db"}},
        }
    )
    assert config.backend.model == "cli"
    assert config.backend.timeout == 120


def test_validation_error_propagates_from_load(xdg_env: Path, env: Environment) -> None:
    del xdg_env
    broken = _full_required("m")
    del broken["backend"]["api_key"]
    _write_yaml(env.get_user_config_file(), broken)
    with pytest.raises(ConfigValidationError) as excinfo:
        ConfigLoader(env=env).load()
    assert any("backend.api_key" in message for message in excinfo.value.errors)


def test_default_environment_is_used_when_env_omitted(xdg_env: Path) -> None:
    user_file = Path(xdg_env) / "home" / ".config" / "komin" / "config.yaml"
    _write_yaml(user_file, _full_required(_USER_MODEL))
    config = ConfigLoader().load()
    assert config.backend.model == _USER_MODEL


def test_load_and_validate_within_startup_budget(xdg_env: Path, env: Environment) -> None:
    del xdg_env
    full = _full_required("gpt-4o")
    full["backend"]["models"] = ["gpt-4o", "gpt-4o-mini"]
    full["backend"]["extra_headers"] = {"X-Custom-Header": "value"}
    full["display"] = {"theme": "default", "spinner": True, "max_width": 0}
    full["logging"] = {"level": "info", "audit": True}
    _write_yaml(env.get_user_config_file(), full)

    loader = ConfigLoader(env=env)
    loader.load()

    timer = Timer()
    timer.start()
    config = loader.load()
    elapsed = timer.elapsed_ms()

    assert config.backend.model == "gpt-4o"
    assert elapsed < 20.0
