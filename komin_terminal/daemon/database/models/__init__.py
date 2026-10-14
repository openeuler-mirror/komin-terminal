"""ORM models for the komin daemon database.

Importing this package registers every model on :data:`Base.metadata` so
that ``create_all`` discovers all tables.
"""

from komin_terminal.daemon.database.models.base import (
    Base,
    BaseModel,
    SchemaVersion,
    utc_now,
)
from komin_terminal.daemon.database.models.chat import ChatModel
from komin_terminal.daemon.database.models.history import HistoryModel, InteractionModel

__all__ = [
    "Base",
    "BaseModel",
    "ChatModel",
    "HistoryModel",
    "InteractionModel",
    "SchemaVersion",
    "utc_now",
]
