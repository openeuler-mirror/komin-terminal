"""Tests for the ``komind`` daemon entry point (fully offline)."""

from __future__ import annotations

import os
import signal
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from komin_terminal.daemon import komind

_SECRET_API_KEY: str = "sk-supersecret-value"


@pytest.fixture(autouse=True)
def _guard_signals() -> Iterator[None]:
    """Save/restore SIGTERM/SIGINT and keep the test process from dying.

    A SIG_IGN safety net is installed first so that a bug in the daemon's
    handler installation can never terminate the whole pytest process.
    """
    originals = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, signal.SIG_IGN)
    yield
    for signum, handler in originals.items():
        signal.signal(signum, handler)


def _write_yaml(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _valid_config_data(tmp_path: Path) -> dict[str, Any]:
    return {
        "backend": {
            "url": "http://localhost:8000/v1",
            "api_key": "sk-test",
            "model": "test-model",
        },
        "database": {
            "type": "sqlite",
            "sqlite": {"path": str(tmp_path / "komind.db")},
        },
    }


def test_missing_required_field_exits_1_without_leaking_secret(
    xdg_env: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del xdg_env
    data = _valid_config_data(tmp_path)
    del data["backend"]["model"]
    data["backend"]["api_key"] = _SECRET_API_KEY
    config_file = _write_yaml(tmp_path / "config.yaml", data)

    rc = komind.main(["--config", str(config_file)])

    stderr = capsys.readouterr().err
    assert rc == 1
    assert "backend.model" in stderr
    assert _SECRET_API_KEY not in stderr


def test_broken_yaml_exits_1_with_path(
    xdg_env: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del xdg_env
    config_file = tmp_path / "broken.yaml"
    config_file.write_text('backend:\n  url: "unclosed\n', encoding="utf-8")

    rc = komind.main(["--config", str(config_file)])

    stderr = capsys.readouterr().err
    assert rc == 1
    assert str(config_file) in stderr


def test_happy_path_starts_server_and_returns_0(
    xdg_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del xdg_env
    config_file = _write_yaml(tmp_path / "config.yaml", _valid_config_data(tmp_path))
    server = MagicMock()
    monkeypatch.setattr(komind, "KominDBusServer", lambda config: server)

    rc = komind.main(["--config", str(config_file)])

    assert rc == 0
    server.start.assert_called_once_with()
    server.stop.assert_called()


def test_sigterm_triggers_stop(
    xdg_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del xdg_env
    config_file = _write_yaml(tmp_path / "config.yaml", _valid_config_data(tmp_path))

    started = threading.Event()
    released = threading.Event()
    stop_calls: list[int] = []

    class _BlockingServer:
        def __init__(self, config: Any) -> None:
            del config

        def start(self) -> None:
            started.set()
            released.wait(timeout=5)

        def stop(self) -> None:
            stop_calls.append(1)
            released.set()

    monkeypatch.setattr(komind, "KominDBusServer", _BlockingServer)

    def _send_sigterm() -> None:
        assert started.wait(timeout=5)
        os.kill(os.getpid(), signal.SIGTERM)

    sender = threading.Thread(target=_send_sigterm)
    sender.start()
    rc = komind.main(["--config", str(config_file)])
    sender.join(timeout=5)

    assert rc == 0
    assert stop_calls, "stop() was not called on SIGTERM"


def test_version_prints_and_exits_0(xdg_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    del xdg_env
    from komin_terminal import __version__

    rc = komind.main(["--version"])

    stdout = capsys.readouterr().out
    assert rc == 0
    assert f"komin-terminal {__version__}" in stdout


def test_debug_forces_debug_logging_level(
    xdg_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del xdg_env
    config_file = _write_yaml(tmp_path / "config.yaml", _valid_config_data(tmp_path))
    captured: dict[str, Any] = {}

    def _factory(config: Any) -> MagicMock:
        captured["config"] = config
        return MagicMock()

    monkeypatch.setattr(komind, "KominDBusServer", _factory)

    rc = komind.main(["--debug", "--config", str(config_file)])

    assert rc == 0
    assert captured["config"].logging.level == "debug"
