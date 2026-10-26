"""Fixtures for the CLI command tests (fully offline).

:class:`FakeKominClient` mirrors the :class:`KominClient` surface used by the
commands layer: namespace proxies, signal subscription and daemon
availability. It is fully programmable and records every call.
"""

from __future__ import annotations

import io
import itertools
import sys
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from komin_terminal.exceptions import DBusCommunicationError


def make_entry(
    *,
    entry_id: str | None = None,
    question: str = "问题",
    response: str = "回答",
    model: str = "test-model",
    created_at: str = "2026-08-20T10:00:00+00:00",
) -> dict[str, Any]:
    """Build one InteractionEntry structure in D-Bus wire form.

    Args:
        entry_id: Interaction id; a random UUID when omitted.
        question: Question text.
        response: Answer text.
        model: Model that produced the answer.
        created_at: ISO-8601 creation timestamp.

    Returns:
        The structure as a dict.
    """
    return {
        "id": entry_id or str(uuid.uuid4()),
        "history_id": str(uuid.uuid4()),
        "question": question,
        "response": response,
        "model": model,
        "tokens_used": 0,
        "created_at": created_at,
    }


class FakeChatProxy:
    """Programmable stand-in for the daemon chat service proxy."""

    def __init__(self, owner: FakeKominClient) -> None:
        self._owner = owner
        self.ask_calls: list[dict[str, Any]] = []
        self.create_calls: list[tuple[str, str, str]] = []
        self.delete_calls: list[str] = []
        self.chats: list[dict[str, Any]] = []
        self.chunks: list[str] = ["你好，世界"]
        self.ask_error: Exception | None = None
        self.stream_error: str | None = None
        self._answer_ids = (f"answer-{index}" for index in itertools.count())
        self._chat_ids = (str(uuid.uuid4()) for _ in itertools.count())

    def ask_question(
        self, question: str, chat_id: str, attachments: list[str], model: str = ""
    ) -> str:
        """Record the call and synchronously emit the programmed stream."""
        self.ask_calls.append(
            {
                "question": question,
                "chat_id": chat_id,
                "attachments": list(attachments),
                "model": model,
            }
        )
        if self.ask_error is not None:
            raise self.ask_error
        answer_id = next(self._answer_ids)
        for chunk in self.chunks:
            self._owner.emit("StreamChunk", answer_id, chunk)
        if self.stream_error is not None:
            self._owner.emit("StreamError", answer_id, self.stream_error)
        else:
            self._owner.emit("StreamEnd", answer_id)
        return answer_id

    def create_chat(self, name: str, description: str, model: str = "") -> str:
        """Record the call and create a fake chat."""
        self.create_calls.append((name, description, model))
        chat_id = next(self._chat_ids)
        self.chats.append(
            {
                "id": chat_id,
                "user_id": str(uuid.uuid4()),
                "name": name,
                "description": description,
                "model": model,
                "created_at": "2026-08-20T10:00:00+00:00",
                "updated_at": "2026-08-20T10:00:00+00:00",
            }
        )
        return chat_id

    def delete_chat(self, chat_id: str) -> bool:
        """Record the call and remove the chat when known."""
        self.delete_calls.append(chat_id)
        for chat in self.chats:
            if chat["id"] == chat_id:
                self.chats.remove(chat)
                return True
        return False

    def list_chats(self) -> list[dict[str, Any]]:
        """Return a copy of every known chat."""
        return list(self.chats)

    def get_chat(self, chat_id: str) -> dict[str, Any]:
        """Return one chat or raise KeyError like the real client mapping."""
        for chat in self.chats:
            if chat["id"] == chat_id:
                return dict(chat)
        raise KeyError(chat_id)


class FakeHistoryProxy:
    """Programmable stand-in for the daemon history service proxy."""

    def __init__(self) -> None:
        self.history_calls: list[tuple[str, int, int]] = []
        self.clear_calls: list[str] = []
        self.restore_calls: list[str] = []
        self.restore_results: dict[str, bool] = {}
        self.entries: list[dict[str, Any]] = []

    def get_history(self, filter: str, offset: int, limit: int) -> list[dict[str, Any]]:
        """Record the call and slice the programmed entries."""
        self.history_calls.append((filter, offset, limit))
        return list(self.entries[offset : offset + limit])

    def clear_history(self, chat_id: str) -> bool:
        """Record the call and clear the programmed entries."""
        self.clear_calls.append(chat_id)
        deleted = bool(self.entries)
        self.entries = []
        return deleted

    def restore_history(self, history_id: str) -> bool:
        """Record the call and return the programmed result."""
        self.restore_calls.append(history_id)
        return self.restore_results.get(history_id, False)

    def get_interaction(self, interaction_id: str) -> dict[str, Any]:
        """Return one entry or raise KeyError."""
        for entry in self.entries:
            if entry["id"] == interaction_id:
                return dict(entry)
        raise KeyError(interaction_id)


class FakeKominClient:
    """In-memory :class:`KominClient` with programmable streaming and CRUD."""

    def __init__(self) -> None:
        self.chat = FakeChatProxy(self)
        self.history = FakeHistoryProxy()
        self.available = True
        self._subscriptions: dict[str, list[Callable[..., None]]] = {}

    def subscribe_signal(
        self, path: str, interface: str, member: str, callback: Callable[..., None]
    ) -> None:
        """Record a signal subscription for later :meth:`emit` delivery."""
        del path, interface
        self._subscriptions.setdefault(member, []).append(callback)

    def emit(self, member: str, *args: Any) -> None:
        """Deliver a signal to every subscriber of ``member``."""
        for callback in list(self._subscriptions.get(member, ())):
            callback(*args)

    def is_daemon_available(self) -> bool:
        """Return the programmed availability."""
        return self.available

    def ensure_daemon(self) -> None:
        """Raise when the daemon is programmed as unreachable."""
        if not self.available:
            raise DBusCommunicationError("komind is not reachable on the system bus")


@pytest.fixture
def fake_client() -> FakeKominClient:
    """Provide a programmable in-memory daemon client."""
    return FakeKominClient()


@pytest.fixture
def stdin_pipe(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], io.StringIO]:
    """Return a factory installing the given text as piped stdin."""

    def _set(content: str) -> io.StringIO:
        buffer = io.StringIO(content)
        monkeypatch.setattr(sys, "stdin", buffer)
        return buffer

    return _set


@pytest.fixture
def scripted_input(monkeypatch: pytest.MonkeyPatch) -> Callable[[list[str]], None]:
    """Return a factory scripting ``input()`` with one line per call."""

    def _set(values: list[str]) -> None:
        iterator = iter(values)

        def fake_input(prompt: str = "") -> str:
            del prompt
            return next(iterator)

        monkeypatch.setattr("builtins.input", fake_input)

    return _set


@pytest.fixture
def cli_main(
    monkeypatch: pytest.MonkeyPatch, fake_client: FakeKominClient
) -> Callable[..., int]:
    """Return ``cli.main`` bound to the fake client factory."""
    import komin_terminal.commands.cli as cli_module

    monkeypatch.setattr(cli_module, "client_factory", lambda: fake_client)
    return lambda argv: cli_module.main(argv)
