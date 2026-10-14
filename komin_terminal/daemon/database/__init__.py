"""Database layer: engine manager, ORM models and user-scoped repositories."""

from komin_terminal.daemon.database.manager import DatabaseManager
from komin_terminal.daemon.database.models import (
    Base,
    BaseModel,
    ChatModel,
    HistoryModel,
    InteractionModel,
    SchemaVersion,
)
from komin_terminal.daemon.database.repository import (
    BaseRepository,
    ChatRepository,
    HistoryRepository,
    InteractionRepository,
)

__all__ = [
    "Base",
    "BaseModel",
    "BaseRepository",
    "ChatModel",
    "ChatRepository",
    "DatabaseManager",
    "HistoryModel",
    "HistoryRepository",
    "InteractionModel",
    "InteractionRepository",
    "SchemaVersion",
]
