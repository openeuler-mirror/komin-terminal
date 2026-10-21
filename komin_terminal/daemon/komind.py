"""Daemon entry point for the ``komind`` system service.

Assembles the validated configuration, logging and the D-Bus server into a
foreground process. Production deployments are activated by systemd
(``Type=dbus``); this module deliberately avoids double-forking so it can be
run directly during development.
"""

from __future__ import annotations

import argparse
import signal
import sys
from collections.abc import Sequence
from pathlib import Path
from types import FrameType
from typing import Any

from komin_terminal import __version__
from komin_terminal.config import ConfigLoader, KominConfig
from komin_terminal.dbus.server import KominDBusServer
from komin_terminal.exceptions import ConfigError, ConfigValidationError
from komin_terminal.logger import get_logger, setup_logging

_LOGGER = get_logger("komin.daemon.komind")

_EXIT_OK: int = 0
_EXIT_CONFIG_ERROR: int = 1
_EXIT_UNEXPECTED: int = 2


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse the daemon command-line arguments.

    Args:
        argv: Argument vector, typically ``sys.argv[1:]``.

    Returns:
        The parsed namespace carrying ``config``, ``debug`` and ``version``.
    """
    parser = argparse.ArgumentParser(
        prog="komind",
        description="Komin-Terminal AI assistant daemon (foreground).",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help="configuration file to load exclusively, replacing the default paths",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="equivalent to logging.level=debug",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"komin-terminal {__version__}",
    )
    return parser.parse_args(list(argv))


def build_config(args: argparse.Namespace) -> KominConfig:
    """Build the application configuration from the parsed arguments.

    ``--debug`` becomes a highest-precedence ``logging.level=debug`` override;
    ``--config`` loads the given file exclusively (default system/user paths
    are ignored).

    Args:
        args: Namespace produced by :func:`parse_args`.

    Returns:
        The fully merged and validated configuration object.

    Raises:
        ConfigError: When the configuration file cannot be read or parsed.
        ConfigValidationError: When the merged configuration is invalid.
    """
    cli_overrides: dict[str, Any] = {}
    if args.debug:
        cli_overrides["logging"] = {"level": "debug"}

    loader = ConfigLoader()
    if args.config:
        return loader.load(cli_overrides, system_file=Path(args.config))
    return loader.load(cli_overrides)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the daemon until signalled to stop.

    Args:
        argv: Argument vector; defaults to ``sys.argv[1:]``.

    Returns:
        ``0`` on a clean shutdown, ``1`` for configuration errors and ``2``
        for any unexpected failure.
    """
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return _EXIT_OK
        return int(code) if isinstance(code, int) else _EXIT_UNEXPECTED

    setup_logging("debug" if args.debug else "info")

    try:
        config = build_config(args)
    except ConfigValidationError as exc:
        for error in exc.errors:
            print(f"komind: configuration error: {error}", file=sys.stderr)
        return _EXIT_CONFIG_ERROR
    except ConfigError as exc:
        print(f"komind: configuration error: {exc.message}", file=sys.stderr)
        if exc.detail:
            print(f"komind: {exc.detail}", file=sys.stderr)
        return _EXIT_CONFIG_ERROR

    try:
        server = KominDBusServer(config)

        def _handle_signal(signum: int, frame: FrameType | None) -> None:
            del signum, frame
            server.stop()

        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)

        _LOGGER.info("komind starting")
        try:
            server.start()
        finally:
            server.stop()
        _LOGGER.info("komind stopped cleanly")
        return _EXIT_OK
    except Exception as exc:  # noqa: BLE001 - boundary: report and exit 2
        print(f"komind: unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return _EXIT_UNEXPECTED


if __name__ == "__main__":
    raise SystemExit(main())
