"""History management: listing, filtering, clearing and restoring records.

The commands here map onto the daemon history service: :ref:`GetHistory
<interfaces>`, :ref:`ClearHistory <interfaces>` and the restore interface
added in this phase. Date constraints (``--since``/``--until``) are applied
client-side because the daemon service does not expose them.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from komin_terminal.commands import format_timestamp, short_display_id, truncate_text
from komin_terminal.commands.cli import argument, command
from komin_terminal.dbus.client import KominClient
from komin_terminal.exceptions import KominError
from komin_terminal.rendering.renderers import Renderers

_DATE_HINT: str = "（日期格式：YYYY-MM-DD）"
_CONFIRM_PROMPT: str = "确认清除全部历史？[y/N] "


def _parse_date_bound(value: str | None) -> datetime | None:
    """Parse a ``YYYY-MM-DD`` bound as a naive-day UTC datetime.

    Args:
        value: The raw ``--since``/``--until`` value.

    Returns:
        The timezone-aware bound, or ``None`` when absent.

    Raises:
        KominError: When the value cannot be parsed.
    """
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as exc:
        raise KominError(f"无效日期 {value!r}{_DATE_HINT}") from exc


def _entry_time(entry: dict[str, Any]) -> datetime:
    """Extract the creation time of an interaction entry as UTC datetime.

    Args:
        entry: InteractionEntry structure as a dict.

    Returns:
        The timezone-aware creation timestamp; naive timestamps are treated
        as UTC.
    """
    parsed = datetime.fromisoformat(str(entry["created_at"]))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


@command("history", "管理问答历史：列表 / 清除 / 恢复")
@argument("--filter", dest="filter_kw", metavar="K", default="", help="按关键词过滤（问题与回答）")
@argument("--since", metavar="DATE", default=None, help="起始日期（含）")
@argument("--until", metavar="DATE", default=None, help="结束日期（含）")
@argument("--page", type=int, default=1, help="页码（从 1 开始）")
@argument("--page-size", type=int, default=20, help="每页条数")
@argument("--clear", action="store_true", help="清除全部历史（软删）")
@argument("--yes", action="store_true", help="跳过清除确认")
@argument(
    "--restore", dest="restore_history_id", metavar="HISTORY_ID", default=None,
    help="恢复软删记录",
)
def run_history(
    args: argparse.Namespace, client: KominClient, renderers: Renderers
) -> int:
    """Execute the history command.

    The default branch renders a paginated table (question truncated to 60
    columns, ids short-displayed to 8 characters). ``--clear`` asks for
    confirmation unless ``--yes`` is given; ``--restore`` undoes a clear for
    one record.

    Args:
        args: Parsed arguments.
        client: Daemon client proxy.
        renderers: Feedback renderers.

    Returns:
        Process exit code (0 success, 1 error).
    """
    client.ensure_daemon()
    if args.clear:
        return _run_clear(args, client, renderers)
    if args.restore_history_id:
        return _run_restore(args.restore_history_id, client, renderers)
    return _run_list(args, client, renderers)


def _fetch_filtered(args: argparse.Namespace, client: KominClient) -> list[dict[str, Any]]:
    """Fetch one page of history and apply client-side date filtering.

    Args:
        args: Parsed arguments.
        client: Daemon client proxy.

    Returns:
        The filtered entries.

    Raises:
        KominError: When a date bound is malformed.
    """
    since = _parse_date_bound(args.since)
    until = _parse_date_bound(args.until)
    if args.page < 1 or args.page_size < 1:
        raise KominError("--page 与 --page-size 必须为正整数")
    offset = (args.page - 1) * args.page_size
    entries = client.history.get_history(args.filter_kw or "", offset, args.page_size)
    filtered: list[dict[str, Any]] = []
    until_exclusive = until + timedelta(days=1) if until is not None else None
    for entry in entries:
        created = _entry_time(entry)
        if since is not None and created < since:
            continue
        if until_exclusive is not None and created >= until_exclusive:
            continue
        filtered.append(entry)
    return filtered


def _render_history_table(entries: list[dict[str, Any]]) -> str:
    """Render a plain-text table of interactions.

    Args:
        entries: InteractionEntry structures as dicts, newest first.

    Returns:
        The rendered table text.
    """
    header = f"{'ID':<8}  {'时间':<16}  {'模型':<14}  {'问题':<60}"
    lines = [header, "-" * len(header)]
    for entry in entries:
        lines.append(
            f"{short_display_id(str(entry.get('id', ''))):<8}  "
            f"{format_timestamp(str(entry.get('created_at', ''))):<16}  "
            f"{truncate_text(str(entry.get('model', '')), 14):<14}  "
            f"{truncate_text(str(entry.get('question', '')), 60):<60}"
        )
    return "\n".join(lines)


def _run_list(
    args: argparse.Namespace, client: KominClient, renderers: Renderers
) -> int:
    """Render the paginated history table on stdout.

    Args:
        args: Parsed arguments.
        client: Daemon client proxy.
        renderers: Feedback renderers.

    Returns:
        Exit code 0 on success, 1 on invalid filter arguments.
    """
    entries = _fetch_filtered(args, client)
    if not entries:
        renderers.notification("没有历史记录")
        return 0
    sys.stdout.write(_render_history_table(entries) + "\n")
    return 0


def _run_clear(
    args: argparse.Namespace, client: KominClient, renderers: Renderers
) -> int:
    """Clear all history after an interactive confirmation.

    Args:
        args: Parsed arguments.
        client: Daemon client proxy.
        renderers: Feedback renderers.

    Returns:
        Exit code 0.
    """
    if not args.yes:
        try:
            answer = input(_CONFIRM_PROMPT)
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if not answer.strip().lower().startswith("y"):
            renderers.notification("已取消")
            return 0
    deleted = bool(client.history.clear_history(""))
    renderers.notification("历史已清除" if deleted else "没有可清除的历史")
    return 0


def _run_restore(
    history_id: str, client: KominClient, renderers: Renderers
) -> int:
    """Restore one soft-deleted history record.

    Args:
        history_id: The interaction id shown in history tables.
        client: Daemon client proxy.
        renderers: Feedback renderers.

    Returns:
        Exit code 0 on success, 1 when no record was restored.
    """
    try:
        restored = bool(client.history.restore_history(history_id))
    except KeyError:
        renderers.error(f"无效的历史 ID: {history_id}")
        return 1
    if not restored:
        renderers.error(f"没有可恢复的历史记录: {history_id}")
        return 1
    renderers.notification(f"已恢复历史记录 {history_id}")
    return 0
