"""Caller authorization for every server-side D-Bus method."""

from __future__ import annotations

from komin_terminal.daemon.session import UserSessionManager
from komin_terminal.dbus.bus import BusAbstraction
from komin_terminal.exceptions import AccessDeniedError, DBusCommunicationError, KominError


class Authorization:
    """Resolve and verify the identity of D-Bus callers.

    Args:
        bus: Bus abstraction used to resolve caller UIDs.
        sessions: User identity manager deriving stable user ids from UIDs.
    """

    def __init__(self, bus: BusAbstraction, sessions: UserSessionManager) -> None:
        """Initialize the authorizer."""
        self._bus = bus
        self._sessions = sessions

    def get_caller_uid(self, connection_name: str) -> int:
        """Resolve the real Unix UID of a caller connection.

        Args:
            connection_name: D-Bus connection name such as ``:1.42``.

        Returns:
            The caller's Unix UID.

        Raises:
            DBusCommunicationError: When the UID cannot be resolved.
        """
        try:
            return int(self._bus.get_caller_uid(connection_name))
        except KominError:
            raise
        except Exception as exc:  # noqa: BLE001 - boundary mapping
            raise DBusCommunicationError(
                f"cannot resolve UID of caller {connection_name}", detail=str(exc)
            ) from exc

    def check_access(self, connection_name: str, claimed_user_id: str | None = None) -> int:
        """Authorize a caller and return its real Unix UID.

        Args:
            connection_name: D-Bus connection name of the caller.
            claimed_user_id: Optional user id claimed by the caller; when
                provided it must match the id derived from the real UID.

        Returns:
            The caller's real Unix UID.

        Raises:
            AccessDeniedError: When the claimed user id does not match.
            DBusCommunicationError: When the UID cannot be resolved.
        """
        uid = self.get_caller_uid(connection_name)
        if claimed_user_id is not None:
            actual = self._sessions.get_user_id(uid)
            if str(actual) != claimed_user_id:
                raise AccessDeniedError(
                    f"caller uid {uid} does not own user id {claimed_user_id}"
                )
        return uid
