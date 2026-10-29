"""Replace {vendor} placeholders in text files for release builds.

This script is invoked during ``%build`` in the RPM spec. It recursively
scans the repository root, replacing every literal ``{vendor}`` in text
files with the RPM ``%{_vendor}`` macro value. Binary files are silently
skipped.

Usage::

    python scripts/prepare_release.py --vendor acme
    python scripts/prepare_release.py --root /tmp/buildroot --vendor acme --dry-run
"""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from pathlib import Path

_VENDOR_RE = re.compile(r"\{vendor\}")

# D-Bus segment: lowercase alphanumeric and hyphens, no leading/trailing hyphen.
_VENDOR_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def substitute_vendor(
    root: Path,
    vendor: str,
    *,
    dry_run: bool = False,
) -> list[Path]:
    """Recursively replace ``{vendor}`` in text files under *root*.

    Args:
        root: Directory to scan recursively.
        vendor: Replacement string for ``{vendor}``.
        dry_run: When ``True``, report files that would be modified without
            writing to disk.

    Returns:
        A list of files that were (or would be) modified.
    """
    modified: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        # Skip binary files: if the content contains a NUL byte, skip.
        if b"\x00" in raw:
            continue
        text = raw.decode("utf-8")
        if "{vendor}" not in text:
            continue
        new_text = text.replace("{vendor}", vendor)
        modified.append(path)
        if not dry_run:
            path.write_text(new_text, encoding="utf-8")
    return modified


def _validate_vendor(vendor: str) -> bool:
    """Return ``True`` if *vendor* is a valid D-Bus segment."""
    return bool(_VENDOR_PATTERN.match(vendor))


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the CLI.

    Args:
        argv: Command-line arguments; ``sys.argv[1:]`` when ``None``.

    Returns:
        Exit code: ``0`` on success, ``1`` on error.
    """
    args = list(sys.argv[1:]) if argv is None else list(argv)

    root: Path | None = None
    vendor: str | None = None
    dry_run = False

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--root" and i + 1 < len(args):
            root = Path(args[i + 1]).resolve()
            i += 2
        elif arg == "--vendor" and i + 1 < len(args):
            vendor = args[i + 1]
            i += 2
        elif arg == "--dry-run":
            dry_run = True
            i += 1
        elif arg in ("-h", "--help"):
            print(
                "Usage: prepare_release.py --vendor <str> [--root <dir>] [--dry-run]",
                file=sys.stderr,
            )
            return 0
        else:
            print(f"Unknown argument: {arg}", file=sys.stderr)
            return 1

    if vendor is None:
        print("Error: --vendor is required", file=sys.stderr)
        return 1

    if not _validate_vendor(vendor):
        print(
            f"Error: invalid vendor {vendor!r} (must be lowercase alphanumeric/hyphens)",
            file=sys.stderr,
        )
        return 1

    if root is None:
        # Detect repo root from this script's location.
        root = Path(__file__).resolve().parent.parent

    modified = substitute_vendor(root, vendor, dry_run=dry_run)
    if modified:
        label = "Would modify" if dry_run else "Modified"
        for path in modified:
            print(f"{label}: {path}")
    else:
        print("No files containing {vendor} found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
