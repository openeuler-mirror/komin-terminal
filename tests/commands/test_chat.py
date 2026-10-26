"""Tests for the chat command: one-shot, pipe input, attachments and REPL."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from komin_terminal.commands import chat as chat_module
from tests.commands.conftest import FakeKominClient


def test_one_shot_streams_and_renders(
    cli_main: Any, fake_client: FakeKominClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """A one-shot question renders the streamed chunks to stdout."""
    fake_client.chat.chunks = ["你好，", "世界"]
    code = cli_main(["你好？"])
    assert code == 0
    assert "你好，世界" in capsys.readouterr().out
    call = fake_client.chat.ask_calls[0]
    assert call["chat_id"] == ""


def test_pipe_input_merges_into_question(
    cli_main: Any, fake_client: FakeKominClient, stdin_pipe: Any
) -> None:
    """Piped stdin becomes a question context block."""
    stdin_pipe("ps aux 输出")
    code = cli_main(["分析一下"])
    assert code == 0
    question = fake_client.chat.ask_calls[0]["question"]
    assert question.startswith("分析一下")
    assert "[管道输入]" in question
    assert "ps aux 输出" in question


def test_attachments_good_oversized_and_missing(
    cli_main: Any,
    fake_client: FakeKominClient,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Valid attachments join the question; invalid ones warn and are skipped."""
    good = tmp_path / "note.txt"
    good.write_text("附件正文内容", encoding="utf-8")
    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * (1024 * 1024 + 1))
    missing = tmp_path / "absent.txt"

    code = cli_main(
        ["chat", "-a", str(good), "-a", str(big), "-a", str(missing), "帮我读附件"]
    )

    assert code == 0
    question = fake_client.chat.ask_calls[0]["question"]
    assert "帮我读附件" in question
    assert "[附件内容]" in question
    assert "附件正文内容" in question
    captured = capsys.readouterr()
    assert captured.out
    stderr = captured.err
    assert str(big) in stderr
    assert str(missing) in stderr
    assert stderr.count("跳过") == 2


def test_stream_error_returns_1(
    cli_main: Any, fake_client: FakeKominClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """A StreamError from the daemon surfaces with exit code 1."""
    fake_client.chat.stream_error = "backend exploded"
    code = cli_main(["q"])
    assert code == 1
    assert "backend exploded" in capsys.readouterr().err


def test_interactive_multi_turn_repl(
    cli_main: Any, fake_client: FakeKominClient, scripted_input: Any
) -> None:
    """The REPL reuses one chat id across turns and exits on /exit."""
    fake_client.chat.chunks = ["答"]
    scripted_input(["第一问", "第二问", "第三问", "/exit"])
    code = cli_main(["chat", "-i"])
    assert code == 0
    assert len(fake_client.chat.create_calls) == 1
    chat_id = fake_client.chat.chats[0]["id"]
    assert [call["chat_id"] for call in fake_client.chat.ask_calls] == [chat_id] * 3


def test_interactive_with_name_creates_chat(
    cli_main: Any, fake_client: FakeKominClient, scripted_input: Any
) -> None:
    """`-i --name` creates a named chat with its description."""
    scripted_input(["/exit"])
    code = cli_main(["chat", "-i", "--name", "ops", "--description", "运维会话"])
    assert code == 0
    assert fake_client.chat.create_calls == [("ops", "运维会话", "")]


def test_interactive_reuses_switched_default_chat(
    cli_main: Any,
    fake_client: FakeKominClient,
    scripted_input: Any,
    xdg_env: Path,
) -> None:
    """`chat --switch` records the default session reused by later `-i` runs."""
    chat_id = fake_client.chat.create_chat("storage", "", "")
    assert cli_main(["chat", "--switch", chat_id]) == 0
    scripted_input(["问一下", "/exit"])
    code = cli_main(["chat", "-i"])
    assert code == 0
    assert len(fake_client.chat.create_calls) == 1
    assert fake_client.chat.ask_calls[0]["chat_id"] == chat_id


def test_switch_unknown_chat_returns_1(
    cli_main: Any, fake_client: FakeKominClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """Switching to a nonexistent chat fails with exit code 1."""
    code = cli_main(["chat", "--switch", "missing-id"])
    assert code == 1
    assert "会话不存在" in capsys.readouterr().err


def test_list_chats_renders_table(
    cli_main: Any, fake_client: FakeKominClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """`chat --list` renders known chats on stdout."""
    chat_id = fake_client.chat.create_chat("ops", "desc", "")
    code = cli_main(["chat", "--list"])
    assert code == 0
    out = capsys.readouterr().out
    assert chat_id[:8] in out
    assert "ops" in out


def test_no_spinner_disables_spinner(
    cli_main: Any, fake_client: FakeKominClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--no-spinner passes enabled=False to the Spinner constructor."""
    started: list[dict[str, object]] = []

    class SpySpinner:
        """Recording stand-in for the Spinner class."""

        def __init__(self, message: str = "思考中", enabled: bool = True, **kwargs: object) -> None:
            del kwargs
            started.append({"message": message, "enabled": enabled})

        def start(self) -> None:
            """No-op."""

        def stop(self) -> None:
            """No-op."""

    monkeypatch.setattr(chat_module, "Spinner", SpySpinner)
    code = cli_main(["chat", "--no-spinner", "q"])
    assert code == 0
    assert started and started[0]["enabled"] is False
