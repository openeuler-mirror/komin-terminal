"""Tests for the chat service interface."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from komin_terminal.daemon.database import (
    DatabaseManager,
    HistoryRepository,
    InteractionRepository,
)
from komin_terminal.daemon.http import StreamEvent
from komin_terminal.daemon.session import UserSessionManager
from komin_terminal.dbus.interfaces import ChatInterface
from komin_terminal.exceptions import AccessDeniedError, AuthenticationError
from tests.dbus.conftest import CALLER_A, CALLER_B, DEFAULT_MODEL, UID_A
from tests.dbus.fakes import FakeBus, FakeQueryExecutor, wait_until


def _await_terminal(bus: FakeBus, answer_id: str) -> None:
    assert wait_until(
        lambda: any(args[0] == answer_id for args in bus.signals("StreamEnd"))
        or any(args[0] == answer_id for args in bus.signals("StreamError"))
    ), "stream did not terminate in time"


def _ask(
    chat_interface: ChatInterface,
    bus: FakeBus,
    question: str = "how do I check load?",
    chat_id: str = "",
    attachments: list[str] | None = None,
    caller: str = CALLER_A,
) -> str:
    answer_id = chat_interface.ask_question(question, chat_id, attachments or [], caller)
    _await_terminal(bus, answer_id)
    return answer_id


def test_ask_question_streams_and_persists(
    chat_interface: ChatInterface,
    bus: FakeBus,
    executor: FakeQueryExecutor,
    db_manager: DatabaseManager,
    sessions: UserSessionManager,
) -> None:
    chat_id = chat_interface.create_chat("ops", "ops chat", CALLER_A)
    executor.stream_events = [
        StreamEvent(kind="chunk", content="use "),
        StreamEvent(kind="chunk", content="uptime"),
        StreamEvent(kind="done"),
    ]

    answer_id = _ask(chat_interface, bus, chat_id=chat_id)

    assert bus.signals("StreamChunk") == [(answer_id, "use "), (answer_id, "uptime")]
    assert bus.signals("StreamEnd") == [(answer_id,)]
    assert bus.signals("StreamError") == []

    user_id = sessions.get_user_id(UID_A)
    histories = HistoryRepository(db_manager, user_id).list()
    assert len(histories) == 1
    assert histories[0].chat_id == uuid.UUID(chat_id)
    interactions = InteractionRepository(db_manager, user_id).filter()
    assert len(interactions) == 1
    assert interactions[0].question == "how do I check load?"
    assert interactions[0].response == "use uptime"
    assert interactions[0].model == DEFAULT_MODEL
    assert interactions[0].tokens_used == 0


def test_executor_error_emits_stream_error(
    chat_interface: ChatInterface, bus: FakeBus, executor: FakeQueryExecutor
) -> None:
    executor.stream_exception = AuthenticationError("invalid api key", status_code=401)
    answer_id = _ask(chat_interface, bus)
    errors = bus.signals("StreamError")
    assert errors and errors[0][0] == answer_id
    assert "invalid api key" in errors[0][1]
    assert bus.signals("StreamEnd") == []


def test_stream_error_event_emits_stream_error(
    chat_interface: ChatInterface, bus: FakeBus, executor: FakeQueryExecutor
) -> None:
    executor.stream_events = [
        StreamEvent(kind="chunk", content="partial"),
        StreamEvent(kind="error", content="backend exploded"),
    ]
    answer_id = _ask(chat_interface, bus)
    errors = bus.signals("StreamError")
    assert errors and errors[0][0] == answer_id
    assert "backend exploded" in errors[0][1]


def test_chat_crud_and_soft_delete(chat_interface: ChatInterface, bus: FakeBus) -> None:
    chat_id = chat_interface.create_chat("alpha", "first chat", CALLER_A)

    listed = chat_interface.list_chats(CALLER_A)
    assert len(listed) == 1
    assert listed[0]["name"] == "alpha"
    assert listed[0]["id"] == chat_id

    fetched = chat_interface.get_chat(chat_id, CALLER_A)
    assert fetched["id"] == chat_id
    assert fetched["description"] == "first chat"

    assert chat_interface.delete_chat(chat_id, CALLER_A) is True
    assert chat_interface.list_chats(CALLER_A) == []
    with pytest.raises(KeyError):
        chat_interface.get_chat(chat_id, CALLER_A)
    assert chat_interface.delete_chat(chat_id, CALLER_A) is False


def test_cross_user_access_denied(chat_interface: ChatInterface, bus: FakeBus) -> None:
    chat_id = chat_interface.create_chat("private", "", CALLER_A)
    with pytest.raises(AccessDeniedError):
        chat_interface.get_chat(chat_id, CALLER_B)
    with pytest.raises(AccessDeniedError):
        chat_interface.ask_question("q", chat_id, [], CALLER_B)
    assert chat_interface.list_chats(CALLER_B) == []


def test_attachment_content_reaches_context(
    chat_interface: ChatInterface,
    bus: FakeBus,
    executor: FakeQueryExecutor,
    tmp_path: Path,
) -> None:
    attachment = tmp_path / "note.txt"
    attachment.write_text("attachment body", encoding="utf-8")
    _ask(chat_interface, bus, attachments=[str(attachment)])
    user_message = executor.queries[-1].messages[-1]["content"]
    assert "attachment body" in user_message


def test_oversized_attachment_emits_stream_error(
    chat_interface: ChatInterface, bus: FakeBus, tmp_path: Path
) -> None:
    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * (1024 * 1024 + 1))
    answer_id = _ask(chat_interface, bus, attachments=[str(big)])
    errors = bus.signals("StreamError")
    assert errors and errors[0][0] == answer_id
    assert "1 MiB" in errors[0][1]


def test_missing_attachment_emits_stream_error(
    chat_interface: ChatInterface, bus: FakeBus, tmp_path: Path
) -> None:
    answer_id = _ask(chat_interface, bus, attachments=[str(tmp_path / "absent.txt")])
    errors = bus.signals("StreamError")
    assert errors and errors[0][0] == answer_id
    assert "not an existing regular file" in errors[0][1]


def test_nonexistent_chat_raises_key_error(chat_interface: ChatInterface) -> None:
    with pytest.raises(KeyError):
        chat_interface.ask_question("q", str(uuid.uuid4()), [], CALLER_A)
    with pytest.raises(KeyError):
        chat_interface.ask_question("q", "not-a-uuid", [], CALLER_A)


def test_history_summary_via_llm_and_persisted(
    chat_interface: ChatInterface,
    bus: FakeBus,
    executor: FakeQueryExecutor,
    db_manager: DatabaseManager,
    sessions: UserSessionManager,
) -> None:
    chat_id = chat_interface.create_chat("long", "", CALLER_A)
    first = _ask(chat_interface, bus, question="first question", chat_id=chat_id)
    assert first

    executor.ask_result = "SUMMARY-TEXT"
    executor.stream_events = [StreamEvent(kind="chunk", content="second"), StreamEvent(kind="done")]
    _ask(chat_interface, bus, question="second question", chat_id=chat_id)

    assert executor.ask_queries, "expected an LLM summarization call"
    summary_prompt = executor.ask_queries[-1].messages[-1]["content"]
    assert "first question" in summary_prompt

    user_message = executor.queries[-1].messages[-1]["content"]
    assert "SUMMARY-TEXT" in user_message

    user_id = sessions.get_user_id(UID_A)
    interactions = InteractionRepository(db_manager, user_id).filter()
    newest = interactions[0]
    assert newest.question.startswith("second question")
    assert "SUMMARY-TEXT" in newest.question
    assert newest.response == "second"


def test_one_shot_question_has_no_chat(
    chat_interface: ChatInterface,
    bus: FakeBus,
    db_manager: DatabaseManager,
    sessions: UserSessionManager,
) -> None:
    _ask(chat_interface, bus, question="standalone")
    user_id = sessions.get_user_id(UID_A)
    histories = HistoryRepository(db_manager, user_id).list()
    assert len(histories) == 1
    assert histories[0].chat_id is None


def test_summary_input_truncated_to_recent_rounds(
    chat_interface: ChatInterface,
    bus: FakeBus,
    executor: FakeQueryExecutor,
    db_manager: DatabaseManager,
    sessions: UserSessionManager,
) -> None:
    chat_id = chat_interface.create_chat("busy", "", CALLER_A)
    user_id = sessions.get_user_id(UID_A)
    history = HistoryRepository(db_manager, user_id).add(chat_id=uuid.UUID(chat_id))
    interactions = InteractionRepository(db_manager, user_id)
    for index in range(25):
        interactions.append_interaction(
            history.id, f"question {index}", f"answer {index}", "m", 0
        )

    _ask(chat_interface, bus, question="next", chat_id=chat_id)

    assert executor.ask_queries, "expected an LLM summarization call"
    summary_prompt = executor.ask_queries[-1].messages[-1]["content"]
    assert summary_prompt.count("用户:") == 20
    assert "question 24" in summary_prompt
    assert "question 4" not in summary_prompt
