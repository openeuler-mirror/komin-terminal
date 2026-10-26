"""Terminal capture package: PTY recording and ANSI stream cleaning.

Public surface: :class:`TerminalReader`, :class:`TerminalParser` and
:func:`get_last_recording` — the building blocks of feature F4 (terminal
output capture used as question context).
"""

from komin_terminal.terminal.parser import TerminalParser
from komin_terminal.terminal.reader import TerminalReader, get_last_recording

__all__ = [
    "TerminalParser",
    "TerminalReader",
    "get_last_recording",
]
