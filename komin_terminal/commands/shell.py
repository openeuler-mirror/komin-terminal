"""``km shell``: interactive terminal recording and recording playback.

Feature F4 — the shell subcommand records one interactive session into a
permission-shielded file (``--enable-record``) or replays the most recent
recording with ANSI sequences cleaned (``--show-last``). Recorded content is
never sent to the daemon unless the user passes ``--with-output`` to a chat
question.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from komin_terminal.commands.cli import argument, command
from komin_terminal.exceptions import TerminalCaptureError
from komin_terminal.rendering.pager import paginate
from komin_terminal.rendering.renderers import Renderers
from komin_terminal.terminal.parser import TerminalParser
from komin_terminal.terminal.reader import TerminalReader, get_last_recording

_USAGE_MESSAGE: str = "用法：km shell --enable-record 开始录制；km shell --show-last 查看最近录制"


@command("shell", "终端输出捕获：录制交互会话或查看最近录制")
@argument("--enable-record", action="store_true", help="录制一次交互 shell 会话（PTY）")
@argument("--show-last", action="store_true", help="显示最近一次的录制内容（已清洗 ANSI）")
def run_shell(args: argparse.Namespace, renderers: Renderers) -> int:
    """Run the shell subcommand: record, show the last recording, or hint.

    Args:
        args: Parsed arguments (``--enable-record`` / ``--show-last``).
        renderers: Feedback renderers.

    Returns:
        Exit code: the recorded shell's exit code for ``--enable-record``,
        ``1`` for capture errors, ``0`` otherwise.
    """
    if args.enable_record and args.show_last:
        renderers.error("--enable-record 与 --show-last 不能同时使用")
        return 1
    if args.enable_record:
        return _run_record(renderers)
    if args.show_last:
        return _show_last(renderers)
    renderers.notification(_USAGE_MESSAGE)
    return 0


def _run_record(renderers: Renderers) -> int:
    """Record one session and notify where it was saved.

    Args:
        renderers: Feedback renderers.

    Returns:
        The recorded shell's exit code, or ``1`` on a capture error.
    """
    try:
        reader = TerminalReader()
        code = reader.run()
    except TerminalCaptureError as error:
        renderers.error(error.message)
        return 1
    renderers.notification(f"会话已结束，录制保存至: {reader.record_path}")
    return code


def _show_last(renderers: Renderers) -> int:
    """Display the newest recording through the pager, cleaned of ANSI.

    Args:
        renderers: Feedback renderers.

    Returns:
        Exit code ``0`` (including the no-recording case, which is reported
        as a warning), ``1`` when the recording cannot be read.
    """
    path = get_last_recording()
    if path is None:
        renderers.warning("暂无可显示的录制记录（先用 km shell --enable-record 录制）")
        return 0
    try:
        text = _read_cleaned(path)
    except TerminalCaptureError as error:
        renderers.error(error.message)
        return 1
    paginate(text)
    return 0


def _read_cleaned(path: Path) -> str:
    """Read one recording file and return its cleaned visible text.

    Args:
        path: Recording file to read.

    Returns:
        The cleaned text.

    Raises:
        TerminalCaptureError: If the file cannot be read.
    """
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise TerminalCaptureError(
            f"无法读取录制文件: {path}", detail=str(error)
        ) from error
    return TerminalParser().parse(raw)
