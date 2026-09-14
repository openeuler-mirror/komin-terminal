"""Tests for komin_terminal.logger."""

from __future__ import annotations

import json
import logging
import sys

import pytest
from komin_terminal import logger as logger_module


@pytest.fixture(autouse=True)
def _clean_root_logging():
    root = logging.getLogger()
    original_handlers = set(root.handlers)
    original_level = root.level
    yield
    for handler in list(root.handlers):
        if handler not in original_handlers:
            root.removeHandler(handler)
    root.setLevel(original_level)
    logging.getLogger("komin.audit").disabled = False


@pytest.mark.parametrize(
    ("level_name", "expected"),
    [
        ("debug", logging.DEBUG),
        ("info", logging.INFO),
        ("warning", logging.WARNING),
        ("error", logging.ERROR),
    ],
)
def test_setup_logging_levels(level_name: str, expected: int) -> None:
    logger_module.setup_logging(level=level_name)
    assert logging.getLogger().level == expected


def test_setup_logging_accepts_uppercase_level() -> None:
    logger_module.setup_logging(level="DEBUG")
    assert logging.getLogger().level == logging.DEBUG


def test_invalid_level_falls_back_to_info(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(logger_module, "_journald_handler", lambda: None)
    logger_module.setup_logging(level="verbose")
    assert logging.getLogger().level == logging.INFO
    captured = capfd.readouterr()
    assert "verbose" in captured.err


def test_fallback_to_stderr_without_journald(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(logger_module, "_journald_handler", lambda: None)
    logger_module.setup_logging(level="info")
    root = logging.getLogger()
    stream_handlers = [
        handler for handler in root.handlers if isinstance(handler, logging.StreamHandler)
    ]
    assert stream_handlers, "expected a stderr StreamHandler fallback"
    assert stream_handlers[0].stream is sys.stderr
    logger_module.get_logger("komin.test").info("fallback-check")
    captured = capfd.readouterr()
    assert "fallback-check" in captured.err


def test_journald_handler_used_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = logging.NullHandler()
    monkeypatch.setattr(logger_module, "_journald_handler", lambda: sentinel)
    logger_module.setup_logging(level="info")
    assert sentinel in logging.getLogger().handlers


def test_setup_logging_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logger_module, "_journald_handler", lambda: None)
    logger_module.setup_logging()
    logger_module.setup_logging()
    assert len(logging.getLogger().handlers) == 1


def test_setup_logging_audit_flag() -> None:
    logger_module.setup_logging(audit=False)
    assert logging.getLogger("komin.audit").disabled
    logger_module.setup_logging(audit=True)
    assert not logging.getLogger("komin.audit").disabled


def test_get_logger_returns_named_logger() -> None:
    log = logger_module.get_logger("komin.demo")
    assert isinstance(log, logging.Logger)
    assert log.name == "komin.demo"


@pytest.mark.parametrize(
    "sensitive_key", ["api_key", "password", "authorization", "secret", "X_API_KEY"]
)
def test_audit_log_strips_sensitive_keys(
    caplog: pytest.LogCaptureFixture, sensitive_key: str
) -> None:
    with caplog.at_level(logging.INFO, logger="komin.audit"):
        logger_module.audit_log("session.start", user="alice", **{sensitive_key: "hunter2"})
    records = [record for record in caplog.records if record.name == "komin.audit"]
    assert len(records) == 1
    message = records[0].getMessage()
    payload = json.loads(message)
    assert payload["event"] == "session.start"
    assert payload["user"] == "alice"
    assert sensitive_key not in payload
    assert "hunter2" not in message


def test_audit_log_strips_sensitive_values(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="komin.audit"):
        logger_module.audit_log("session.start", note="my password is hunter2")
    records = [record for record in caplog.records if record.name == "komin.audit"]
    assert len(records) == 1
    message = records[0].getMessage()
    payload = json.loads(message)
    assert "note" not in payload
    assert "hunter2" not in message


def test_audit_log_emits_valid_json_with_event(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="komin.audit"):
        logger_module.audit_log("daemon.start", pid=42)
    records = [record for record in caplog.records if record.name == "komin.audit"]
    payload = json.loads(records[0].getMessage())
    assert payload == {"event": "daemon.start", "pid": 42}


def test_audit_log_record_extra_fields(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="komin.audit"):
        logger_module.audit_log("daemon.start")
    record = next(r for r in caplog.records if r.name == "komin.audit")
    assert record.SYSLOG_IDENTIFIER == "komind"
    assert record.KOMIN_AUDIT == "1"
