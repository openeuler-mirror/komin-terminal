"""End-to-end offline daemon flow: AskQuestion -> streaming signals -> database.

Assembles the real :class:`KominDBusServer` with the in-memory ``FakeBus``,
the programmable ``FakeQueryExecutor`` and a temporary SQLite database. No
real D-Bus system bus, network or systemd is touched.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from komin_terminal.config import (
    BackendConfig,
    DatabaseConfig,
    DisplayConfig,
    KominConfig,
    LoggingConfig,
)
from komin_terminal.constants import get_dbus_chat_namespace, get_dbus_object_path_chat
from komin_terminal.daemon.database import HistoryRepository, InteractionRepository
from komin_terminal.daemon.http import StreamEvent
from komin_terminal.dbus.server import KominDBusServer
from tests.dbus.fakes import FakeBus, FakeQueryExecutor, wait_until

pytestmark = pytest.mark.integration

CALLER: str = ":1.99"
CALLER_UID: int = 4321
MACHINE_ID: str = "0123456789abcdef0123456789abcdef"
QUESTION_ONE: str = "如何查看系统负载？"
QUESTION_TWO: str = "如何清理磁盘空间？"
CHUNKS: tuple[str, ...] = ("负载", "可用 uptime 查看")
MODEL: str = "test-model"


def _expected_user_id(uid: int) -> uuid.UUID:
    return uuid.uuid5(uuid.uuid5(uuid.NAMESPACE_DNS, MACHINE_ID), str(uid))


def _config(tmp_path: Path) -> KominConfig:
    return KominConfig(
        backend=BackendConfig(url="http://localhost:8000/v1", api_key="sk-test", model=MODEL),
        database=DatabaseConfig(type="sqlite", sqlite_path=tmp_path / "komind.db"),
        display=DisplayConfig(),
        logging=LoggingConfig(),
    )


@pytest.fixture
def daemon(xdg_env: Path) -> Iterator[tuple[Any, ...]]:
    """Start the real daemon with FakeBus and a fake executor.

    Yields:
        A ``(server, bus, executor)`` tuple; the server is stopped on
        teardown.
    """
    bus = FakeBus()
    bus.set_caller_uid(CALLER, CALLER_UID)
    bus.caller = CALLER

    executor = FakeQueryExecutor(
        stream_events=[
            *[StreamEvent(kind="chunk", content=chunk) for chunk in CHUNKS],
            StreamEvent(kind="done"),
        ]
    )
    server = KominDBusServer(_config(xdg_env), bus=bus)
    server._executor_factory = lambda: executor  # noqa: SLF001 - test injection

    thread = threading.Thread(target=server.start, daemon=True, name="komin-test-server")
    thread.start()
    assert wait_until(lambda: len(bus.requested_names) == 3), "server did not start in time"

    yield server, bus, executor

    server.stop()
    thread.join(timeout=5)
    assert not thread.is_alive(), "server thread leaked"


def _ask(bus: FakeBus, question: str) -> str:
    proxy = bus.get_proxy(get_dbus_chat_namespace(), get_dbus_object_path_chat())
    return str(proxy.AskQuestion(question, "", [], ""))


def test_ask_question_streams_and_persists(daemon: tuple[Any, ...]) -> None:
    server, bus, executor = daemon

    chunks: list[tuple[str, str]] = []
    ended: list[str] = []
    errors: list[tuple[str, str]] = []
    bus.subscribe_signal(
        get_dbus_object_path_chat(),
        get_dbus_chat_namespace(),
        "StreamChunk",
        lambda answer_id, content: chunks.append((answer_id, content)),
    )
    bus.subscribe_signal(
        get_dbus_object_path_chat(),
        get_dbus_chat_namespace(),
        "StreamEnd",
        lambda answer_id: ended.append(answer_id),
    )
    bus.subscribe_signal(
        get_dbus_object_path_chat(),
        get_dbus_chat_namespace(),
        "StreamError",
        lambda answer_id, message: errors.append((answer_id, message)),
    )

    answer_id = _ask(bus, QUESTION_ONE)
    assert wait_until(lambda: answer_id in ended), f"no StreamEnd: errors={errors}"
    assert errors == []

    assert [content for aid, content in chunks if aid == answer_id] == list(CHUNKS)

    user_id = _expected_user_id(CALLER_UID)
    db = server.database
    assert db is not None

    histories = HistoryRepository(db, user_id).list(limit=10)
    assert len(histories) == 1
    assert histories[0].user_id == user_id

    interactions = InteractionRepository(db, user_id).filter(limit=10)
    assert len(interactions) == 1
    assert interactions[0].question == QUESTION_ONE
    assert interactions[0].response == "".join(CHUNKS)
    assert interactions[0].model == MODEL

    second_answer_id = _ask(bus, QUESTION_TWO)
    assert wait_until(lambda: second_answer_id in ended), "no StreamEnd for second question"

    assert len(HistoryRepository(db, user_id).list(limit=10)) == 2
    second_interactions = InteractionRepository(db, user_id).filter(limit=10)
    assert len(second_interactions) == 2
    newest = second_interactions[0]
    assert newest.question == QUESTION_TWO
    assert newest.response == "".join(CHUNKS)

    assert executor.queries, "fake executor was never invoked"

    assert wait_until(
        lambda: (
            not any(
                t.name.startswith("komin-stream-") and t.is_alive() for t in threading.enumerate()
            )
        )
    ), "streaming threads leaked"
