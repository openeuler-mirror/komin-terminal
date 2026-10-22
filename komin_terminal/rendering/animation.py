"""Loading spinner animation.

The spinner draws braille frames from a daemon thread. It stays completely
silent when disabled or when the output stream is not a tty, so piped output
is never polluted.
"""

from __future__ import annotations

import sys
import threading
from typing import IO

FRAMES: tuple[str, ...] = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
"""Braille animation frames."""


def _is_tty(stream: IO[str]) -> bool:
    """Return True when ``stream`` is an interactive terminal."""
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


class Spinner:
    """A terminal loading spinner with a background animation thread."""

    def __init__(
        self,
        message: str = "思考中",
        enabled: bool = True,
        stream: IO[str] = sys.stderr,
        interval: float = 0.1,
    ) -> None:
        """Initialize the spinner.

        Args:
            message: Text shown next to the animated frame.
            enabled: When ``False``, :meth:`start` is a no-op.
            stream: Output sink; defaults to stderr. Animation only runs
                when the stream is a tty.
            interval: Seconds between frames.
        """
        self._message = message
        self._enabled = enabled
        self._stream = stream
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._animating = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the animation thread.

        No-op when disabled, already running, or when the stream is not a
        tty (pipes, captured output, tests).
        """
        with self._lock:
            if self._thread is not None or not self._enabled:
                return
            if not _is_tty(self._stream):
                return
            self._stop_event.clear()
            self._animating = True
            self._thread = threading.Thread(target=self._run, daemon=True, name="komin-spinner")
            self._thread.start()

    def stop(self) -> None:
        """Stop the animation and clear the residual frame.

        Idempotent: safe to call multiple times or when never started.
        Waits for the animation thread to exit, then erases the frame with
        ``\\r\\x1b[K``.
        """
        with self._lock:
            thread = self._thread
            animating = self._animating
            self._thread = None
            self._animating = False
        if thread is None:
            return
        self._stop_event.set()
        thread.join()
        if animating:
            try:
                self._stream.write("\r\x1b[K")
                self._stream.flush()
            except ValueError:
                pass

    def __enter__(self) -> Spinner:
        """Start the spinner when entering the context."""
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        """Stop the spinner when leaving the context.

        Args:
            exc: Exception information (unused).
        """
        del exc
        self.stop()

    def _run(self) -> None:
        """Animation loop executed on the background thread."""
        index = 0
        while True:
            frame = FRAMES[index % len(FRAMES)]
            try:
                self._stream.write(f"\r\x1b[K{frame} {self._message}")
                self._stream.flush()
            except ValueError:
                return
            index += 1
            if self._stop_event.wait(self._interval):
                return
