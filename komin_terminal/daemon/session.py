"""User identity management for the daemon.

Maps a UNIX UID to a stable, machine-scoped :class:`UserIdentity` using a
nested UUID5 derivation so the id survives re-installs as long as the
machine-id does.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from komin_terminal.utils.environment import Environment


@dataclass(frozen=True)
class UserIdentity:
    """Identity binding a UNIX UID to a stable machine-scoped user id."""

    user_id: uuid.UUID
    unix_uid: int


class UserSessionManager:
    """Generate and cache user identities.

    The machine-id is read once and cached for the lifetime of the manager;
    derived identities are cached per UID.
    """

    def __init__(self, env: Environment | None = None) -> None:
        """Initialize the manager.

        Args:
            env: Environment provider; a fresh instance is created when
                ``None`` is passed.
        """
        self._env = env if env is not None else Environment()
        self._machine_id: str | None = None
        self._identities: dict[int, UserIdentity] = {}

    def get_user_id(self, unix_uid: int) -> uuid.UUID:
        """Return the stable user id for a UNIX UID.

        The derivation is ``uuid5(uuid5(NAMESPACE_DNS, machine_id), str(uid))``.
        The machine-id is read once and cached.

        Args:
            unix_uid: The caller's UNIX UID.

        Returns:
            The deterministic, machine-scoped user id.
        """
        if self._machine_id is None:
            self._machine_id = self._env.get_machine_id()
        return uuid.uuid5(uuid.uuid5(uuid.NAMESPACE_DNS, self._machine_id), str(unix_uid))

    def get_identity(self, unix_uid: int) -> UserIdentity:
        """Return the cached :class:`UserIdentity` for a UNIX UID.

        Args:
            unix_uid: The caller's UNIX UID.

        Returns:
            The identity object for the UID.
        """
        identity = self._identities.get(unix_uid)
        if identity is None:
            identity = UserIdentity(user_id=self.get_user_id(unix_uid), unix_uid=unix_uid)
            self._identities[unix_uid] = identity
        return identity

    def clear_cache(self) -> None:
        """Drop the cached machine-id and every cached identity."""
        self._machine_id = None
        self._identities.clear()


__all__ = ["UserIdentity", "UserSessionManager"]
