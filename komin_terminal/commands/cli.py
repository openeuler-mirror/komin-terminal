"""CLI entry point: parsing, routing and unified error handling.

Design notes:

- Every heavy dependency (D-Bus client, rendering stack, configuration) is
  initialized lazily after argument routing so trivial commands such as
  ``km --version`` stay within the SRS latency budget.
- Exit codes: ``0`` success, ``1`` :class:`KominError` (friendly message on
  stderr), ``2`` argument errors and unexpected exceptions.
- Command handlers register themselves through the :func:`command` /
  :func:`argument` decorators; :func:`build_parser` imports the command
  modules on demand to assemble the parser.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Callable, Sequence
from typing import Any

from komin_terminal import __version__
from komin_terminal.exceptions import KominError

_SUBCOMMAND_MODULES: dict[str, str] = {
    "chat": "komin_terminal.commands.chat",
    "history": "komin_terminal.commands.history",
    "shell": "komin_terminal.commands.shell",
}

_COMMANDS: dict[str, dict[str, Any]] = {}
_PENDING_ARGUMENTS: list[tuple[tuple[str, ...], dict[str, Any]]] = []


def command(name: str, help: str) -> Callable[[Callable[..., int]], Callable[..., int]]:
    """Register a subcommand handler, capturing any pending declarations.

    Args:
        name: Subcommand name as given on the command line.
        help: One-line help text shown by ``--help``.

    Returns:
        A decorator that registers the handler into the command table.
    """

    def register(func: Callable[..., int]) -> Callable[..., int]:
        _COMMANDS[name] = {
            "func": func,
            "help": help,
            "arguments": list(_PENDING_ARGUMENTS),
        }
        _PENDING_ARGUMENTS.clear()
        return func

    return register


def argument(*flags: str, **kwargs: Any) -> Callable[[Callable[..., int]], Callable[..., int]]:
    """Declare an argparse option for the next registered command handler.

    Positional and keyword arguments are forwarded verbatim to
    :meth:`argparse.ArgumentParser.add_argument`.

    Args:
        flags: Option strings such as ``"--filter"``.
        kwargs: add_argument keyword arguments.

    Returns:
        A decorator that buffers the declaration until a handler registers.
    """
    _PENDING_ARGUMENTS.append((flags, kwargs))

    def decorate(func: Callable[..., int]) -> Callable[..., int]:
        return func

    return decorate


def _load_command_modules() -> None:
    """Import every command module so they can register themselves."""
    for module_name in _SUBCOMMAND_MODULES.values():
        importlib.import_module(module_name)


def _add_global_options(parser: argparse.ArgumentParser, *, with_version: bool) -> None:
    """Attach the CLI global options to ``parser``.

    Args:
        parser: Parser receiving the options.
        with_version: Include the ``--version`` action.
    """
    if with_version:
        parser.add_argument(
            "--version", action="version", version=f"%(prog)s {__version__}"
        )
    parser.add_argument(
        "--model",
        metavar="M",
        default=None,
        help="指定本次使用的模型（空则沿用 daemon 默认）",
    )
    parser.add_argument("--no-spinner", action="store_true", help="禁用思考中动画")
    parser.add_argument("--debug", action="store_true", help="启用调试日志")


def build_parser() -> argparse.ArgumentParser:
    """Build the full ``km`` parser with every registered subcommand.

    Returns:
        A configured argument parser.
    """
    _load_command_modules()
    parser = argparse.ArgumentParser(
        prog="km",
        description="Komin-Terminal：面向 Linux 系统管理员的 AI 命令行助手。",
    )
    _add_global_options(parser, with_version=True)
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="命令")
    for name in sorted(_COMMANDS):
        spec = _COMMANDS[name]
        common = argparse.ArgumentParser(add_help=False)
        _add_global_options(common, with_version=False)
        child = subparsers.add_parser(name, help=spec["help"], parents=[common])
        for flags, kwargs in spec["arguments"]:
            child.add_argument(*flags, **kwargs)
    return parser


def _normalize_command_line(args: list[str]) -> list[str]:
    """Route bare invocations (``km "question"``) into the chat subcommand.

    Args:
        args: The raw command-line arguments.

    Returns:
        Normalized arguments: every run without an explicit subcommand is
        rewritten as a ``chat`` invocation.
    """
    if not args:
        return args
    if args[0] in ("-h", "--help", "--version") or args[0] in _SUBCOMMAND_MODULES:
        return args
    return ["chat", *args]


def _setup_debug_logging(args: argparse.Namespace) -> None:
    """Enable debug logging when requested.

    Args:
        args: Parsed arguments.
    """
    if not getattr(args, "debug", False):
        return
    from komin_terminal.logger import setup_logging

    setup_logging(level="debug")


def _load_display_config() -> Any:
    """Load the display configuration, falling back to defaults.

    The full configuration requires backend credentials that may not exist on
    a fresh install; the CLI only needs the display section, so any load
    failure degrades silently to the built-in defaults.

    Returns:
        A :class:`DisplayConfig` instance.
    """
    from komin_terminal.config.loader import ConfigLoader
    from komin_terminal.config.schema import DisplayConfig

    try:
        return ConfigLoader().load().display
    except KominError:
        return DisplayConfig()


def _build_renderers(args: Any) -> tuple[Any, Any, bool]:
    """Build the theme-based feedback renderers and markdown renderer.

    Args:
        args: Parsed arguments (only ``--no-spinner`` is consumed here).

    Returns:
        A ``(Renderers, MarkdownRenderer, spinner_enabled)`` tuple.
    """
    from komin_terminal.rendering.markdown import MarkdownRenderer
    from komin_terminal.rendering.renderers import Renderers
    from komin_terminal.rendering.theme import Theme

    display = _load_display_config()
    theme = Theme.load(display.theme)
    renderers = Renderers(theme, stream=sys.stderr)
    renderer = MarkdownRenderer(theme, width=display.max_width)
    spinner_enabled = bool(display.spinner) and not getattr(args, "no_spinner", False)
    return renderers, renderer, spinner_enabled


def _default_client() -> Any:
    """Construct the real D-Bus client (lazy import seeded factory)."""
    from komin_terminal.dbus.client import KominClient

    return KominClient()


client_factory: Callable[[], Any] = _default_client
"""Factory seam for constructing the daemon client; tests replace it."""


def _dispatch(args: argparse.Namespace) -> int:
    """Route parsed arguments to the registered command handler.

    Args:
        args: Parsed arguments.

    Returns:
        The handler's exit code.

    Raises:
        KominError: Friendly, expected failures (mapped to exit code 1).
        Exception: Anything else (mapped to exit code 2 by :func:`main`).
    """
    _setup_debug_logging(args)
    spec = _COMMANDS[args.command]
    if args.command == "shell":
        renderers, _renderer, _spinner = _build_renderers(args)
        return int(spec["func"](args, renderers))
    client = client_factory()
    renderers, renderer, spinner_enabled = _build_renderers(args)
    if args.command == "chat":
        return int(
            spec["func"](args, client, renderers, renderer, spinner_enabled=spinner_enabled)
        )
    return int(spec["func"](args, client, renderers))


def _render_friendly_error(error: KominError) -> None:
    """Write a themed one-line error to stderr.

    Args:
        error: The expected failure.
    """
    try:
        renderers, _renderer, _spinner = _build_renderers(_EmptyArgs())
        renderers.error(error.message)
    except Exception:  # noqa: BLE001 - never mask the original error
        sys.stderr.write(f"error: {error.message}\n")


class _EmptyArgs:
    """Namespace stand-in carrying no CLI options."""


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments, route to a handler and translate exceptions to codes.

    Args:
        argv: Command-line arguments; ``sys.argv[1:]`` when omitted.

    Returns:
        The process exit code (0/1/2).
    """
    args_list = list(sys.argv[1:]) if argv is None else [str(item) for item in argv]

    if args_list == ["--version"]:
        sys.stdout.write(f"km {__version__}\n")
        return 0

    try:
        namespace = build_parser().parse_args(_normalize_command_line(args_list))
        code = _dispatch(namespace)
    except KominError as error:
        _render_friendly_error(error)
        return 1
    except SystemExit:
        raise
    except Exception as error:  # noqa: BLE001 - unified unexpected-error boundary
        sys.stderr.write(f"{type(error).__name__}: {error}\n")
        return 2
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
