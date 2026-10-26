"""Tests for the CLI entry point: parsing, routing and exit codes."""

from __future__ import annotations

from typing import Any

import pytest
from komin_terminal.commands import cli as cli_module
from komin_terminal.exceptions import DBusCommunicationError
from komin_terminal.utils.benchmark import Timer
from tests.commands.conftest import FakeKominClient

_VERSION: str = "1.0.0"


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["chat", "-i"], {"command": "chat", "interactive": True}),
        (["chat", "-i", "--name", "ops"], {"command": "chat", "name": "ops"}),
        (["chat", "-i", "--description", "d"], {"command": "chat", "description": "d"}),
        (["chat", "--list"], {"command": "chat", "list_chats": True}),
        (["chat", "--delete", "abc"], {"command": "chat", "delete_chat_id": "abc"}),
        (["chat", "--switch", "abc"], {"command": "chat", "switch_chat_id": "abc"}),
        (
            ["chat", "-a", "f.txt", "question"],
            {"command": "chat", "attachments": ["f.txt"], "question": ["question"]},
        ),
        (["chat", "--model", "m9", "q"], {"command": "chat", "model": "m9"}),
        (["chat", "--no-spinner", "q"], {"command": "chat", "no_spinner": True}),
        (["history"], {"command": "history", "page": 1, "page_size": 20}),
        (
            [
                "history",
                "--filter",
                "err",
                "--since",
                "2026-08-01",
                "--until",
                "2026-08-31",
                "--page",
                "2",
                "--page-size",
                "5",
            ],
            {
                "command": "history",
                "filter_kw": "err",
                "since": "2026-08-01",
                "until": "2026-08-31",
                "page": 2,
                "page_size": 5,
            },
        ),
        (
            ["history", "--clear", "--yes"],
            {"command": "history", "clear": True, "yes": True},
        ),
        (
            ["history", "--restore", "R1"],
            {"command": "history", "restore_history_id": "R1"},
        ),
        (["shell", "--enable-record"], {"command": "shell", "enable_record": True}),
        (["shell", "--show-last"], {"command": "shell", "show_last": True}),
    ],
)
def test_command_tree_parses_into_namespace(
    argv: list[str], expected: dict[str, Any]
) -> None:
    """Every subcommand/option combination parses into the expected namespace."""
    namespace = cli_module.build_parser().parse_args(argv)
    for key, value in expected.items():
        assert getattr(namespace, key) == value


def test_bare_question_routes_to_chat(
    cli_main: Any, fake_client: FakeKominClient
) -> None:
    """`km "question"` without a subcommand routes to one-shot chat."""
    code = cli_main(["如何查看负载？"])
    assert code == 0
    assert fake_client.chat.ask_calls[0]["question"] == "如何查看负载？"


def test_help_lists_every_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    """--help shows all three subcommands and exits 0."""
    with pytest.raises(SystemExit) as excinfo:
        cli_module.main(["--help"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    for subcommand in ("chat", "history", "shell"):
        assert subcommand in captured.out


def test_version_prints_version_number(capsys: pytest.CaptureFixture[str]) -> None:
    """--version prints the package version and exits 0."""
    code = cli_module.main(["--version"])
    assert code == 0
    assert _VERSION in capsys.readouterr().out


def test_unknown_option_exits_2() -> None:
    """Unknown argument errors surface argparse's exit code 2."""
    with pytest.raises(SystemExit) as excinfo:
        cli_module.main(["--bogus"])
    assert excinfo.value.code == 2


def test_komin_error_yields_friendly_message_and_exit_1(
    cli_main: Any, fake_client: FakeKominClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """KominError becomes a friendly stderr message with exit code 1."""
    fake_client.chat.ask_error = DBusCommunicationError("komind is not reachable")
    code = cli_main(["问题"])
    assert code == 1
    assert "komind is not reachable" in capsys.readouterr().err


def test_unexpected_error_exits_2_without_traceback(
    cli_main: Any, fake_client: FakeKominClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unexpected exceptions print class + summary with exit code 2."""
    fake_client.chat.ask_error = RuntimeError("boom")
    code = cli_main(["问题"])
    assert code == 2
    stderr = capsys.readouterr().err
    assert "RuntimeError" in stderr
    assert "boom" in stderr
    assert "Traceback" not in stderr


def test_version_path_is_fast(capsys: pytest.CaptureFixture[str]) -> None:
    """The SRS latency budget: km --version answers well under 100 ms."""
    timer = Timer()
    timer.start()
    code = cli_module.main(["--version"])
    elapsed = timer.elapsed_ms()
    assert code == 0
    assert elapsed < 100.0
