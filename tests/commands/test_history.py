"""Tests for the history command: table, filters, clear and restore."""

from __future__ import annotations

from typing import Any

import pytest
from tests.commands.conftest import FakeKominClient, make_entry


def test_history_table_truncates_question_and_shortens_id(
    cli_main: Any, fake_client: FakeKominClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """The table shows ids truncated to 8 chars and questions to 60 columns."""
    long_question = "q" * 120
    entry_id = "12345678-9abc-def0-1234-56789abcdef0"
    fake_client.history.entries = [make_entry(entry_id=entry_id, question=long_question)]

    code = cli_main(["history"])
    assert code == 0

    out = capsys.readouterr().out
    assert entry_id[:8] in out
    assert long_question[:60] in out
    assert long_question[:61] not in out


def test_history_filter_and_page_passthrough(
    cli_main: Any, fake_client: FakeKominClient
) -> None:
    """--filter/--page/--page-size translate into GetHistory arguments."""
    cli_main(["history", "--filter", "err", "--page", "2", "--page-size", "5"])
    assert fake_client.history.history_calls == [("err", 5, 5)]


def test_history_since_until_filters_locally(
    cli_main: Any, fake_client: FakeKominClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """--since/--until filter entries by creation time on the client side."""
    fake_client.history.entries = [
        make_entry(question="在区间内", created_at="2026-08-15T10:00:00+00:00"),
        make_entry(question="太早", created_at="2026-08-01T10:00:00+00:00"),
        make_entry(question="太晚", created_at="2026-09-01T10:00:00+00:00"),
    ]
    code = cli_main(["history", "--since", "2026-08-10", "--until", "2026-08-31"])
    assert code == 0
    out = capsys.readouterr().out
    assert "在区间内" in out
    assert "太早" not in out
    assert "太晚" not in out


def test_history_invalid_date_returns_1(
    cli_main: Any, fake_client: FakeKominClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """Malformed date bounds fail with a friendly error and exit code 1."""
    code = cli_main(["history", "--since", "garbage"])
    assert code == 1
    assert "无效日期" in capsys.readouterr().err


def test_history_clear_confirms_with_yes(
    cli_main: Any, fake_client: FakeKominClient, scripted_input: Any
) -> None:
    """`--clear` proceeds when the user answers y."""
    scripted_input(["y"])
    code = cli_main(["history", "--clear"])
    assert code == 0
    assert fake_client.history.clear_calls == [""]


def test_history_clear_aborts_on_no(
    cli_main: Any, fake_client: FakeKominClient, scripted_input: Any
) -> None:
    """`--clear` aborts without calling the daemon when the user answers n."""
    scripted_input(["n"])
    code = cli_main(["history", "--clear"])
    assert code == 0
    assert fake_client.history.clear_calls == []


def test_history_clear_with_yes_skips_prompt(
    cli_main: Any,
    fake_client: FakeKominClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--clear --yes` never calls input()."""

    def failing_input(prompt: str = "") -> str:
        del prompt
        raise AssertionError("input() must not be called with --yes")

    monkeypatch.setattr("builtins.input", failing_input)
    code = cli_main(["history", "--clear", "--yes"])
    assert code == 0
    assert fake_client.history.clear_calls == [""]


def test_history_restore_success(
    cli_main: Any, fake_client: FakeKominClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--restore` forwards the id and reports success."""
    fake_client.history.restore_results["hist-1"] = True
    code = cli_main(["history", "--restore", "hist-1"])
    assert code == 0
    assert fake_client.history.restore_calls == ["hist-1"]
    assert "已恢复" in capsys.readouterr().err


def test_history_restore_missing_returns_1(
    cli_main: Any, fake_client: FakeKominClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """A nonexistent restore target fails with exit code 1."""
    code = cli_main(["history", "--restore", "nope"])
    assert code == 1
    assert "没有可恢复" in capsys.readouterr().err
