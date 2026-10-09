"""Tests for komin_terminal.utils.benchmark."""

from __future__ import annotations

import logging
import time

import pytest
from komin_terminal.exceptions import KominError
from komin_terminal.utils.benchmark import Timer, benchmark


def test_timer_elapsed_ms_increases() -> None:
    timer = Timer()
    timer.start()
    time.sleep(0.01)
    elapsed = timer.elapsed_ms()
    assert elapsed >= 10.0


def test_timer_elapsed_ms_monotonic() -> None:
    timer = Timer()
    timer.start()
    first = timer.elapsed_ms()
    second = timer.elapsed_ms()
    third = timer.elapsed_ms()
    assert first <= second <= third


def test_timer_restart_resets_elapsed() -> None:
    timer = Timer()
    timer.start()
    time.sleep(0.01)
    timer.start()
    assert timer.elapsed_ms() < 10.0


def test_timer_elapsed_before_start_raises() -> None:
    timer = Timer()
    with pytest.raises(KominError):
        timer.elapsed_ms()


def test_benchmark_emits_debug_log(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="komin.benchmark"), benchmark("demo-block"):
        time.sleep(0.001)
    records = [record for record in caplog.records if record.name == "komin.benchmark"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "demo-block" in message
    assert "ms" in message
    assert records[0].levelno == logging.DEBUG


def test_benchmark_logs_even_when_block_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with (
        caplog.at_level(logging.DEBUG, logger="komin.benchmark"),
        pytest.raises(ValueError, match="boom"),
        benchmark("failing-block"),
    ):
        raise ValueError("boom")
    records = [record for record in caplog.records if record.name == "komin.benchmark"]
    assert len(records) == 1
    assert "failing-block" in records[0].getMessage()
