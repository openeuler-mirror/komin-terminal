"""End-to-end capture flow: recording files feed one-shot questions.

F4 closed loop without any real daemon or terminal: a recording file is
placed under the isolated XDG cache directory, then ``km --with-output`` is
run against the programmable fake client and the assembled question is
inspected for the cleaned recording content.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from komin_terminal.utils.environment import Environment
from tests.commands.conftest import FakeKominClient

pytestmark = pytest.mark.integration


@pytest.fixture
def fake_client() -> FakeKominClient:
    """Provide a programmable in-memory daemon client."""
    return FakeKominClient()

@pytest.fixture
def cli_main(
    monkeypatch: pytest.MonkeyPatch, fake_client: FakeKominClient
) -> Callable[..., int]:
    """Return ``cli.main`` bound to the fake client factory."""
    import komin_terminal.commands.cli as cli_module

    monkeypatch.setattr(cli_module, "client_factory", lambda: fake_client)
    return lambda argv: cli_module.main(argv)


def test_with_output_flow_feeds_cleaned_recording(
    cli_main: Any,
    fake_client: FakeKominClient,
    xdg_env: Path,
) -> None:
    """Recent recording content reaches the question after ANSI cleaning."""
    records_dir = Environment().get_user_cache_dir() / "recordings"
    records_dir.mkdir(parents=True, exist_ok=True)
    recording = records_dir / "terminal-20260821-090000-000001.log"
    recording.write_text("磁盘使用 du -sh\n\x1b[32m健康\x1b[0m 检查通过", encoding="utf-8")

    code = cli_main(["分析这些输出", "--with-output"])
    assert code == 0
    question = fake_client.chat.ask_calls[0]["question"]
    assert question.startswith("分析这些输出")
    assert "[终端输出]" in question
    assert "磁盘使用 du -sh" in question
    assert "健康 检查通过" in question
    assert "\x1b[32m" not in question


def test_with_output_flow_without_recording_warns(
    cli_main: Any,
    fake_client: FakeKominClient,
    xdg_env: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No recording yields a warning and a normal question."""
    code = cli_main(["随便问", "--with-output"])
    assert code == 0
    captured = capsys.readouterr()
    assert "没有可用的终端录制内容" in captured.err
    question = fake_client.chat.ask_calls[0]["question"]
    assert question.startswith("随便问")
    assert "[终端输出]" not in question
