"""Base class for D-Bus serializable structures."""

from __future__ import annotations

import dataclasses
import types
import typing
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Self

from komin_terminal.exceptions import DBusCommunicationError


def _encode(value: Any) -> Any:
    """Encode one field value into a D-Bus friendly representation.

    Args:
        value: The field value.

    Returns:
        ``str`` for UUIDs, ISO-8601 ``str`` for datetimes, a dict for nested
        structures, the value unchanged otherwise.
    """
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        stamp = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return stamp.isoformat()
    if isinstance(value, Structure):
        return value.to_structure()
    return value


def _decode(value: Any, target: Any) -> Any:
    """Decode one field value from its D-Bus representation.

    Args:
        value: The wire representation.
        target: The resolved type hint of the destination field.

    Returns:
        The decoded value.

    Raises:
        DBusCommunicationError: When the value cannot be decoded.
    """
    origin = typing.get_origin(target)
    if origin is typing.Union or origin is types.UnionType:
        alternatives = [arg for arg in typing.get_args(target) if arg is not type(None)]
        if value is None:
            return None
        return _decode(value, alternatives[0])
    if target is uuid.UUID:
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except ValueError as exc:
            raise DBusCommunicationError(f"invalid UUID in structure: {value!r}") from exc
    if target is datetime:
        if isinstance(value, datetime):
            parsed = value
        else:
            try:
                parsed = datetime.fromisoformat(str(value))
            except ValueError as exc:
                raise DBusCommunicationError(
                    f"invalid ISO-8601 timestamp in structure: {value!r}"
                ) from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    if isinstance(target, type) and issubclass(target, Structure):
        return target.from_structure(value)
    return value


@dataclasses.dataclass(frozen=True)
class Structure:
    """Base class for frozen dataclasses crossing the D-Bus boundary.

    Serialization rules: ``uuid.UUID`` maps to ``str``, timezone-aware UTC
    datetimes map to ISO-8601 strings, nested structures convert recursively
    and every other value passes through unchanged.
    """

    @classmethod
    def from_structure(cls, data: Mapping[str, Any]) -> Self:
        """Build an instance from its D-Bus representation.

        Args:
            data: Mapping of field names to wire values.

        Returns:
            A new instance of ``cls``.

        Raises:
            DBusCommunicationError: When a field is missing or malformed.
        """
        hints = typing.get_type_hints(cls)
        kwargs: dict[str, Any] = {}
        for field in dataclasses.fields(cls):
            if field.name not in data:
                raise DBusCommunicationError(
                    f"{cls.__name__} structure is missing field {field.name!r}"
                )
            kwargs[field.name] = _decode(data[field.name], hints[field.name])
        return cls(**kwargs)

    def to_structure(self) -> dict[str, Any]:
        """Serialize this instance for transport over D-Bus.

        Returns:
            A dict of field names to wire values.
        """
        result: dict[str, Any] = {}
        for field in dataclasses.fields(self):
            result[field.name] = _encode(getattr(self, field.name))
        return result
