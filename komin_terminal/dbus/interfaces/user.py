"""User service D-Bus interface."""

from __future__ import annotations

from komin_terminal.constants import get_dbus_user_namespace
from komin_terminal.daemon.session import UserSessionManager
from komin_terminal.dbus.bus import InterfaceSpec, MethodSpec
from komin_terminal.dbus.interfaces.authorization import Authorization


class UserInterface:
    """Server-side user identity service published on the D-Bus system bus.

    Args:
        auth: Caller authorizer.
        sessions: User identity manager.
    """

    def __init__(self, *, auth: Authorization, sessions: UserSessionManager) -> None:
        """Initialize the user service."""
        self._auth = auth
        self._sessions = sessions

    def get_dbus_spec(self) -> InterfaceSpec:
        """Return the declarative D-Bus specification of this service."""
        return InterfaceSpec(
            interface_name=get_dbus_user_namespace(),
            methods=(MethodSpec("GetUserId", "get_user_id", (), "s"),),
        )

    def get_user_id(self, caller: str) -> str:
        """Return the stable user id of the caller.

        Args:
            caller: D-Bus connection name of the caller.

        Returns:
            The UUID5 user id derived from the caller's real UID.
        """
        uid = self._auth.check_access(caller)
        return str(self._sessions.get_user_id(uid))

