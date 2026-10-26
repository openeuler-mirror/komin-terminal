"""Pager-backed plain-text display with graceful degradation.

``km shell --show-last`` prints cleaned recording text through this helper:
a real terminal gets ``$PAGER`` (or ``less``) so long output is scrollable,
while any non-tty or pager-less environment receives a direct full dump so
scripted use and CI pipelines are never blocked.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from typing import TextIO


def _resolve_pager() -> list[str] | None:
    """Return the pager command to run, or ``None`` when none is available.

    The ``PAGER`` environment variable wins; otherwise ``less`` is used when
    present on ``PATH``.

    Returns:
        The argv for the pager subprocess, or ``None``.
    """
    pager_spec = os.environ.get("PAGER") or ""
    if pager_spec:
        try:
            return shlex.split(pager_spec)
        except ValueError:
            return None
    if shutil.which("less"):
        return ["less", "-R"]
    return None


def _stream_is_tty(stream: TextIO) -> bool:
    """Return whether the stream is an interactive terminal."""
    try:
        return bool(stream.isatty())
    except (AttributeError, OSError, ValueError):
        return False


def paginate(text: str, *, stream: TextIO | None = None) -> None:
    """Display ``text`` through a pager when interactive, else print it.

    Empty text produces no output. Pager failures (missing executable,
    spawn errors) fall back to a direct dump on ``stream``.

    Args:
        text: The text to display.
        stream: Output stream; ``sys.stdout`` when omitted.
    """
    target = stream or sys.stdout
    if not text:
        return
    if not _stream_is_tty(target):
        _write_direct(target, text)
        return
    command = _resolve_pager()
    if command is None:
        _write_direct(target, text)
        return
    try:
        subprocess.run(command, input=text, text=True, stdin=subprocess.PIPE, check=False)
    except (OSError, ValueError):
        _write_direct(target, text)


def _write_direct(stream: TextIO, text: str) -> None:
    """Write the text verbatim, ensuring a trailing newline."""
    stream.write(text)
    if not text.endswith("\n"):
        stream.write("\n")
    stream.flush()
