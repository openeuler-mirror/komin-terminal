"""History service D-Bus interface."""

from __future__ import annotations

import uuid
from typing import Any

from komin_terminal.constants import (
    get_dbus_history_namespace,
)
from komin_terminal.daemon.database import (
    ChatRepository,
    DatabaseManager,
    HistoryRepository,
    InteractionRepository,
)
from komin_terminal.daemon.session import UserSessionManager
from komin_terminal.dbus.bus import BusAbstraction, InterfaceSpec, MethodSpec
from komin_terminal.dbus.interfaces.authorization import Authorization
from komin_terminal.dbus.structures import InteractionEntry

_CLEAR_BATCH_LIMIT: int = 10_000


class HistoryInterface:
    """Server-side history service published on the D-Bus system bus.

    Every public method starts with a caller authorization check and all
    data access is filtered by the caller's user id.

    Args:
        auth: Caller authorizer.
        sessions: User identity manager.
        db: Database manager.
        bus: Bus abstraction (kept for symmetry and future signals).
    """

    def __init__(
        self,
        *,
        auth: Authorization,
        sessions: UserSessionManager,
        db: DatabaseManager,
        bus: BusAbstraction,
    ) -> None:
        """Initialize the history service."""
        self._auth = auth
        self._sessions = sessions
        self._db = db
        self._bus = bus

    def get_dbus_spec(self) -> InterfaceSpec:
        """Return the declarative D-Bus specification of this service."""
        return InterfaceSpec(
            interface_name=get_dbus_history_namespace(),
            methods=(
                MethodSpec("GetHistory", "get_history", ("s", "i", "i"), "aa{sv}"),
                MethodSpec("ClearHistory", "clear_history", ("s",), "b"),
                MethodSpec("RestoreHistory", "restore_history", ("s",), "b"),
                MethodSpec("GetInteraction", "get_interaction", ("s",), "a{sv}"),
            ),
        )

    def get_history(
        self, filter: str, offset: int, limit: int, caller: str
    ) -> list[dict[str, Any]]:
        """List the caller's interactions, optionally filtered by keyword.

        Args:
            filter: Case-insensitive substring matched against question and
                response; empty disables filtering.
            offset: Number of records to skip.
            limit: Maximum number of records to return.
            caller: D-Bus connection name of the caller.

        Returns:
            InteractionEntry structures as dicts, newest first.
        """
        uid = self._auth.check_access(caller)
        user_id = self._sessions.get_user_id(uid)
        rows = InteractionRepository(self._db, user_id).filter(
            keyword=filter or None, offset=offset, limit=limit
        )
        return [
            InteractionEntry(
                id=row.id,
                history_id=row.history_id,
                question=row.question,
                response=row.response,
                model=row.model,
                tokens_used=row.tokens_used,
                created_at=row.created_at,
            ).to_structure()
            for row in rows
        ]

    def clear_history(self, chat_id: str, caller: str) -> bool:
        """Soft-delete the caller's history records.

        Args:
            chat_id: Restrict clearing to one chat; empty clears everything.
            caller: D-Bus connection name of the caller.

        Returns:
            ``True`` when at least one record was deleted.

        Raises:
            KeyError: When the chat id is malformed.
        """
        uid = self._auth.check_access(caller)
        user_id = self._sessions.get_user_id(uid)
        history_repo = HistoryRepository(self._db, user_id)
        if chat_id:
            try:
                parsed = uuid.UUID(chat_id)
            except ValueError as exc:
                raise KeyError(f"invalid chat id {chat_id!r}") from exc
            if ChatRepository(self._db, user_id).get(parsed) is None:
                return False
            rows = history_repo.list_by_chat(parsed, limit=_CLEAR_BATCH_LIMIT)
        else:
            total = history_repo.count()
            rows = history_repo.list(limit=max(total, 1)) if total else []
        deleted = False
        for row in rows:
            if history_repo.soft_delete(row.id):
                deleted = True
        return deleted

    def restore_history(self, interaction_id: str, caller: str) -> bool:
        """Restore the history record owning an interaction.

        Clearing history soft-deletes the owning history record, which makes
        its interactions disappear from every listing. This method resolves
        the owning history of ``interaction_id`` (including soft-deleted
        histories) and clears the soft-delete marker.

        Args:
            interaction_id: An interaction id, as shown in history tables.
            caller: D-Bus connection name of the caller.

        Returns:
            ``True`` when a deleted history was restored; ``False`` when
            no deleted history exists for this interaction and user.

        Raises:
            KeyError: When the id is malformed.
        """
        uid = self._auth.check_access(caller)
        user_id = self._sessions.get_user_id(uid)
        try:
            parsed = uuid.UUID(interaction_id)
        except ValueError as exc:
            raise KeyError(f"invalid interaction id {interaction_id!r}") from exc
        history_id = InteractionRepository(self._db, user_id).get_owner_history_id(parsed)
        if history_id is None:
            return False
        return HistoryRepository(self._db, user_id).restore(history_id)

    def get_interaction(self, interaction_id: str, caller: str) -> dict[str, Any]:
        """Fetch one interaction owned by the caller.

        Args:
            interaction_id: Interaction to fetch.
            caller: D-Bus connection name of the caller.

        Returns:
            The InteractionEntry structure as a dict.

        Raises:
            KeyError: When the id is malformed, unknown or owned by another
                user.
        """
        uid = self._auth.check_access(caller)
        user_id = self._sessions.get_user_id(uid)
        try:
            parsed = uuid.UUID(interaction_id)
        except ValueError as exc:
            raise KeyError(f"invalid interaction id {interaction_id!r}") from exc
        row = InteractionRepository(self._db, user_id).get(parsed)
        if row is None:
            raise KeyError(f"interaction {interaction_id} not found")
        return InteractionEntry(
            id=row.id,
            history_id=row.history_id,
            question=row.question,
            response=row.response,
            model=row.model,
            tokens_used=row.tokens_used,
            created_at=row.created_at,
        ).to_structure()
