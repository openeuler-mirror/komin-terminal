"""Cross-process data structures exchanged over D-Bus."""

from komin_terminal.dbus.structures.base import Structure
from komin_terminal.dbus.structures.chat import ChatInfo
from komin_terminal.dbus.structures.history import HistoryEntry, InteractionEntry

__all__ = ["ChatInfo", "HistoryEntry", "InteractionEntry", "Structure"]
