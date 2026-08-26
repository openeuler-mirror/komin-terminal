"""Scan project source for hardcoded absolute paths.

Checks ``komin_terminal/**/*.py`` and ``tests/**/*.py`` for developer-machine
absolute paths (``/home/``, ``/root/``, ``/Users/``) and reports violations.
The repository root is resolved from this script's location, never from the
current working directory, so the check is portable.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from pathlib import Path

FORBIDDEN = re.compile(r"/home/|/root/|/Users/")
SCAN_DIRS = ("komin_terminal", "tests")


def find_violations(root: Path) -> list[tuple[Path, int, str]]:
    """Return every forbidden absolute-path occurrence under ``root``.

    Args:
        root: Repository root directory to scan.

    Returns:
        A list of ``(file, line_number, line_text)`` tuples, one per match.
    """
    violations: list[tuple[Path, int, str]] = []
    for directory in SCAN_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if FORBIDDEN.search(line):
                    violations.append((path, lineno, line.strip()))
    return violations


def main(argv: Sequence[str] | None = None) -> int:
    """Run the check and return a process exit code.

    Args:
        argv: Optional argument list. The first element, when present, is the
            repository root to scan; otherwise the root is derived from this
            script's location.

    Returns:
        ``0`` when no hardcoded absolute paths are found, ``1`` otherwise.
    """
    args = list(sys.argv[1:]) if argv is None else list(argv)
    if args:
        root = Path(args[0]).resolve()
    else:
        root = Path(__file__).resolve().parent.parent
    violations = find_violations(root)
    if not violations:
        print("check_no_abs_paths: no hardcoded absolute paths found")
        return 0
    for path, lineno, line in violations:
        shown = path.relative_to(root) if path.is_relative_to(root) else path
        print(f"{shown}:{lineno}: forbidden absolute path: {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
