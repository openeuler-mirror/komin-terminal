"""Chat commands: one-shot streaming questions and interactive sessions.

The chat command delivers F1 (single question, streamed Markdown), F2
(interactive multi-turn sessions), F5 (pipe input) and F6 (file
attachments). All data flows through the :class:`KominClient` D-Bus proxy;
nothing in this module touches the database or the HTTP layer directly.
"""

from __future__ import annotations

import argparse
import select
import sys
import threading
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any

from komin_terminal.commands import format_timestamp, short_display_id, truncate_text
from komin_terminal.commands.cli import argument, command
from komin_terminal.constants import get_dbus_chat_namespace, get_dbus_object_path_chat
from komin_terminal.dbus.client import KominClient
from komin_terminal.rendering.animation import Spinner
from komin_terminal.rendering.markdown import MarkdownRenderer
from komin_terminal.rendering.renderers import Renderers
from komin_terminal.rendering.stream import StreamRenderer
from komin_terminal.utils.environment import get_environment
from komin_terminal.utils.files import write_atomic

_REPL_PROMPT: str = "komin> "
_MAX_ATTACHMENT_BYTES: int = 1_048_576
_STATE_FILE_NAME: str = "default_chat"
_SPINNER_MESSAGE: str = "思考中"
_REPL_HELP: str = (
    "内建命令：/exit 或 /quit 退出，/list 列出会话，"
    "/model <模型名> 切换模型（空则恢复默认），/help 显示本帮助"
)
_MISSING_QUESTION_MESSAGE: str = "请提供问题文本（例如：km 如何查看系统负载？）"


def _state_file_path() -> Path:
    """Return the per-user default-session state file path.

    Returns:
        ``<user_data_dir>/default_chat``.
    """
    return get_environment().get_user_data_dir() / _STATE_FILE_NAME


def read_default_chat_id() -> str:
    """Read the last switched-to default chat id, or an empty string.

    Returns:
        The stored chat id, empty when no state exists or reading fails.
    """
    try:
        return _state_file_path().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _write_default_chat_id(chat_id: str) -> None:
    """Persist the default chat id into the state file.

    Args:
        chat_id: Chat id to store.
    """
    env = get_environment()
    path = env.get_user_data_dir() / _STATE_FILE_NAME
    env.ensure_dir(path.parent)
    write_atomic(path, chat_id + "\n")


def read_pipe_input(timeout: float = 0.1) -> str | None:
    """Read piped stdin content; ``None`` for a tty or an empty pipe.

    Args:
        timeout: Seconds to wait for piped data to become readable.

    Returns:
        The complete piped text, or ``None`` when stdin is a terminal or
        carries no data.
    """
    try:
        is_tty = bool(sys.stdin.isatty())
    except (AttributeError, OSError, ValueError):
        is_tty = False
    if is_tty:
        return None
    try:
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
    except (AttributeError, OSError, TypeError, ValueError):
        ready = [sys.stdin]
    if not ready:
        return None
    try:
        data = sys.stdin.read()
    except OSError:
        return None
    return data or None


def read_attachments(paths: list[Path], max_size: int = _MAX_ATTACHMENT_BYTES) -> str:
    """Read attachment files into one assembled text block.

    Missing files, unreadable files and files larger than ``max_size`` are
    skipped with a warning so a single bad path never blocks the question.

    Args:
        paths: Attachment paths supplied by the user.
        max_size: Per-file byte limit (default 1 MiB).

    Returns:
        The assembled attachment text, possibly empty.
    """
    blocks: list[str] = []
    for path in paths:
        if not path.is_file():
            _warn_attachment(f"跳过不存在的附件: {path}")
            continue
        try:
            if path.stat().st_size > max_size:
                _warn_attachment(f"跳过超过 1 MiB 的附件: {path}")
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            _warn_attachment(f"跳过无法读取的附件: {path}")
            continue
        blocks.append(f"[{path.name}]\n{text}")
    return "\n\n".join(blocks)


def _warn_attachment(message: str) -> None:
    """Write one attachment warning line to stderr."""
    with suppress(OSError):
        sys.stderr.write(f"警告: {message}\n")


def _compose_question(question: str, attachment_paths: list[str]) -> str:
    """Assemble the final question with pipe and attachment context.

    Args:
        question: The user's question text.
        attachment_paths: Attachment paths (already validated by
            :func:`read_attachments`).

    Returns:
        The composed question carrying every available context block.
    """
    parts = [question]
    pipe_text = read_pipe_input()
    if pipe_text:
        parts.append("[管道输入]\n" + pipe_text)
    attachment_texts = read_attachments([Path(path) for path in attachment_paths])
    if attachment_texts:
        parts.append("[附件内容]\n" + attachment_texts)
    return "\n\n".join(parts)


@command("chat", "与 AI 对话：单次问答或交互式会话（默认命令）")
@argument("-i", "--interactive", action="store_true", help="进入交互式多轮会话")
@argument("--name", metavar="N", default=None, help="与会话 -i 联用，创建命名会话")
@argument("--description", metavar="D", default="", help="会话描述（与 --name 联用）")
@argument(
    "-a",
    "--attachment",
    dest="attachments",
    action="append",
    metavar="FILE",
    default=[],
    help="附加文本文件作为上下文（可重复，单个 ≤1 MiB）",
)
@argument("--list", dest="list_chats", action="store_true", help="列出全部会话")
@argument("--delete", dest="delete_chat_id", metavar="CHAT_ID", default=None, help="软删会话")
@argument("--switch", dest="switch_chat_id", metavar="CHAT_ID", default=None, help="切换默认会话")
@argument("question", nargs="*", default=[], help="问题文本（无子命令时可直接 `km 问题`）")
def run_chat(
    args: argparse.Namespace,
    client: KominClient,
    renderers: Renderers,
    renderer: MarkdownRenderer,
    *,
    spinner_enabled: bool = True,
) -> int:
    """Execute the chat command: one-shot, interactive or chat management.

    One-shot mode composes the question with pipe/attachment context, starts
    a streamed question and renders answer chunks incrementally with a
    spinner until the first chunk arrives. Interactive mode runs a REPL
    over a chat whose context is maintained daemon-side.

    Args:
        args: Parsed arguments.
        client: Daemon client proxy.
        renderers: Feedback renderers writing to stderr.
        renderer: Markdown renderer used for streamed answers.
        spinner_enabled: Whether the spinner may animate.

    Returns:
        Process exit code (0 success, 1 error).
    """
    client.ensure_daemon()
    if args.list_chats:
        return _run_list_chats(client)
    if args.delete_chat_id:
        return _run_delete_chat(args.delete_chat_id, client, renderers)
    if args.switch_chat_id:
        return _run_switch_chat(args.switch_chat_id, client, renderers)
    if args.interactive:
        return _run_interactive(args, client, renderers, renderer, spinner_enabled)
    question = " ".join(args.question).strip()
    if not question:
        renderers.error(_MISSING_QUESTION_MESSAGE)
        return 1
    composed = _compose_question(question, args.attachments or [])
    return _ask_once(
        composed, "", args.model or "", client, renderers, renderer, spinner_enabled
    )


def _ask_once(
    question: str,
    chat_id: str,
    model: str,
    client: KominClient,
    renderers: Renderers,
    renderer: MarkdownRenderer,
    spinner_enabled: bool,
) -> int:
    """Run one streamed question and render the answer incrementally.

    Args:
        question: The complete question text.
        chat_id: Chat to attach the exchange to; empty for one-shot.
        model: Optional model override (empty uses the daemon default).
        client: Daemon client proxy.
        renderers: Feedback renderers.
        renderer: Markdown renderer.
        spinner_enabled: Whether the spinner may animate.

    Returns:
        Exit code 0 on success, 1 on StreamError.
    """
    lock = threading.Lock()
    events: list[tuple[str, str, str]] = []
    done = threading.Event()

    def _record(kind: str, answer_id: str, payload: str = "") -> None:
        with lock:
            events.append((kind, answer_id, payload))
        if kind in ("end", "error"):
            done.set()

    client.subscribe_signal(
        get_dbus_object_path_chat(), get_dbus_chat_namespace(), "StreamChunk",
        lambda answer_id, content: _record("chunk", answer_id, content),
    )
    client.subscribe_signal(
        get_dbus_object_path_chat(), get_dbus_chat_namespace(), "StreamEnd",
        lambda answer_id: _record("end", answer_id),
    )
    client.subscribe_signal(
        get_dbus_object_path_chat(), get_dbus_chat_namespace(), "StreamError",
        lambda answer_id, message: _record("error", answer_id, message),
    )

    spinner = Spinner(message=_SPINNER_MESSAGE, enabled=spinner_enabled)
    spinner.start()
    try:
        answer_id = str(client.chat.ask_question(question, chat_id, [], model))
    except Exception:
        spinner.stop()
        raise

    stream_renderer = StreamRenderer(renderer)
    error_message: str | None = None
    spinner_stopped = False
    try:
        while True:
            if not done.is_set():
                done.wait(0.05)
            with lock:
                batch, events[:] = events[:], []
            for kind, event_answer_id, payload in batch:
                if event_answer_id != answer_id:
                    continue
                if not spinner_stopped:
                    spinner.stop()
                    spinner_stopped = True
                if kind == "chunk" and error_message is None:
                    stream_renderer.feed(payload)
                elif kind == "error":
                    error_message = payload
            if done.is_set():
                break
    finally:
        spinner.stop()
    if error_message is not None:
        renderers.error(error_message)
        return 1
    stream_renderer.finish()
    sys.stdout.write("\n")
    return 0


def _render_chat_table(chats: list[dict[str, Any]]) -> str:
    """Render a plain-text table of chats.

    Args:
        chats: ChatInfo structures as dicts.

    Returns:
        The rendered table text.
    """
    header = f"{'ID':<8}  {'名称':<24}  {'模型':<14}  {'创建时间':<16}"
    lines = [header, "-" * len(header)]
    for chat in chats:
        lines.append(
            f"{short_display_id(str(chat.get('id', ''))):<8}  "
            f"{truncate_text(str(chat.get('name', '')), 24):<24}  "
            f"{truncate_text(str(chat.get('model', '')), 14):<14}  "
            f"{format_timestamp(str(chat.get('created_at', ''))):<16}"
        )
    return "\n".join(lines)


def _run_list_chats(client: KominClient) -> int:
    """List every live chat of the current user on stdout.

    Args:
        client: Daemon client proxy.

    Returns:
        Exit code 0.
    """
    chats = client.chat.list_chats()
    if not chats:
        sys.stdout.write("没有会话\n")
        return 0
    sys.stdout.write(_render_chat_table(chats) + "\n")
    return 0


def _run_delete_chat(chat_id: str, client: KominClient, renderers: Renderers) -> int:
    """Soft-delete one chat.

    Args:
        chat_id: Chat to delete.
        client: Daemon client proxy.
        renderers: Feedback renderers.

    Returns:
        Exit code 0 when deleted, 1 otherwise.
    """
    try:
        deleted = bool(client.chat.delete_chat(chat_id))
    except KeyError:
        renderers.error(f"无效的会话 ID: {chat_id}")
        return 1
    if not deleted:
        renderers.error(f"会话不存在: {chat_id}")
        return 1
    renderers.notification(f"已删除会话 {chat_id}")
    return 0


def _run_switch_chat(chat_id: str, client: KominClient, renderers: Renderers) -> int:
    """Switch the default chat used by interactive mode.

    Args:
        chat_id: Chat to make the default.
        client: Daemon client proxy.
        renderers: Feedback renderers.

    Returns:
        Exit code 0 when switched, 1 when the chat is unknown.
    """
    try:
        _ = client.chat.get_chat(chat_id)
    except KeyError:
        renderers.error(f"会话不存在: {chat_id}")
        return 1
    try:
        _write_default_chat_id(chat_id)
    except OSError as error:
        renderers.error(f"无法记录默认会话: {error}")
        return 1
    renderers.notification(f"已切换默认会话: {chat_id}")
    return 0


def _run_interactive(
    args: argparse.Namespace,
    client: KominClient,
    renderers: Renderers,
    renderer: MarkdownRenderer,
    spinner_enabled: bool,
) -> int:
    """Run the interactive REPL over one persistent chat.

    Args:
        args: Parsed arguments (``--name``/``--description``/``--model``).
        client: Daemon client proxy.
        renderers: Feedback renderers.
        renderer: Markdown renderer.
        spinner_enabled: Whether the spinner may animate.

    Returns:
        Exit code 0.
    """
    chat_id = _resolve_session_chat(args, client, renderers)
    model = args.model or ""
    renderers.notification(f"已进入会话 {short_display_id(chat_id)}（/help 查看内建命令）")
    while True:
        try:
            line = input(_REPL_PROMPT)
        except EOFError:
            sys.stdout.write("\n")
            return 0
        except KeyboardInterrupt:
            sys.stdout.write("\n")
            return 0
        text = line.strip()
        if not text:
            continue
        if text in ("/exit", "/quit"):
            return 0
        if text == "/help":
            renderers.notification(_REPL_HELP)
            continue
        if text == "/list":
            sys.stdout.write(_render_chat_table(client.chat.list_chats()) + "\n")
            continue
        if text.startswith("/model"):
            model = text[len("/model"):].strip()
            renderers.notification(f"模型已设为: {model or '默认'}")
            continue
        _ask_once(text, chat_id, model, client, renderers, renderer, spinner_enabled)


def _resolve_session_chat(
    args: argparse.Namespace, client: KominClient, renderers: Renderers
) -> str:
    """Resolve the chat id used by an interactive session.

    Priority: an explicit ``--name`` (always creates), the previously
    switched-to default chat (when it still exists), otherwise a freshly
    created session.

    Args:
        args: Parsed arguments.
        client: Daemon client proxy.
        renderers: Feedback renderers.

    Returns:
        The chat id for the session.
    """
    if args.name:
        chat_id = str(client.chat.create_chat(args.name, args.description or "", args.model or ""))
        renderers.notification(f"已创建会话 {short_display_id(chat_id)}（{args.name}）")
        return chat_id
    default_id = read_default_chat_id()
    if default_id:
        try:
            client.chat.get_chat(default_id)
            return default_id
        except KeyError:
            renderers.warning("默认会话已不存在，创建新会话")
    name = datetime.now().strftime("会话 %Y-%m-%d %H:%M")
    chat_id = str(client.chat.create_chat(name, "", args.model or ""))
    renderers.notification(f"已创建会话 {short_display_id(chat_id)}（{name}）")
    return chat_id
