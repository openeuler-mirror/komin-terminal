"""``km shell`` placeholder: terminal capture arrives in phase 9.

This module keeps the full argument surface (``--enable-record`` /
``--show-last``) so phase 9 can replace the implementation without touching
the parser contract.
"""

from __future__ import annotations

import argparse

from komin_terminal.commands.cli import argument, command
from komin_terminal.rendering.renderers import Renderers

_PLACEHOLDER_MESSAGE: str = "km shell 将在 phase 9 交付 terminal capture 功能"


@command("shell", "捕获终端输出（占位：phase 9 交付）")
@argument("--enable-record", action="store_true", help="开启终端录制（phase 9 生效）")
@argument("--show-last", action="store_true", help="显示上次捕获（phase 9 生效）")
def run_shell(args: argparse.Namespace, renderers: Renderers) -> int:
    """Print the phase-9 placeholder notification and exit successfully.

    Args:
        args: Parsed arguments (accepted but unused in this phase).
        renderers: Feedback renderers.

    Returns:
        Exit code 0.
    """
    del args
    renderers.notification(_PLACEHOLDER_MESSAGE)
    return 0
