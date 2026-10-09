"""Benchmarking helpers for measuring code block durations."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

from komin_terminal.exceptions import KominError

_BENCHMARK_LOGGER_NAME: str = "komin.benchmark"


class Timer:
    """Monotonic timer measuring elapsed milliseconds."""

    def __init__(self) -> None:
        """Initialize the timer in the stopped state."""
        self._started_at: float | None = None

    def start(self) -> None:
        """Start (or restart) the timer."""
        self._started_at = time.perf_counter()

    def elapsed_ms(self) -> float:
        """Return milliseconds elapsed since the last :meth:`start`.

        Returns:
            Elapsed time in milliseconds; monotonically non-decreasing.

        Raises:
            KominError: If :meth:`start` was never called.
        """
        if self._started_at is None:
            raise KominError("Timer was never started")
        return (time.perf_counter() - self._started_at) * 1000.0


@contextmanager
def benchmark(name: str) -> Iterator[None]:
    """Measure a code block's wall-clock duration.

    The elapsed milliseconds are written to the ``komin.benchmark`` logger at
    debug level when the block exits, including on exceptions.

    Args:
        name: Label identifying the measured code block.

    Yields:
        Control to the wrapped block.
    """
    timer = Timer()
    timer.start()
    try:
        yield
    finally:
        logging.getLogger(_BENCHMARK_LOGGER_NAME).debug("%s took %.3f ms", name, timer.elapsed_ms())
