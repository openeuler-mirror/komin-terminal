"""Tests for scripts/check_no_abs_paths.py.

Forbidden path literals are assembled from fragments so that this test file
itself never contains a hardcoded absolute path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_no_abs_paths.py"

HOME_ABS = "/" + "home" + "/alice/notes.txt"
ROOT_ABS = "/" + "root" + "/.config"
USERS_ABS = "/" + "Users" + "/bob/data"


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_no_abs_paths", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_no_abs_paths"] = module
    spec.loader.exec_module(module)
    return module


_checker = _load_checker()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_clean_tree_returns_zero(tmp_path: Path) -> None:
    _write(tmp_path / "komin_terminal" / "clean.py", "value = 'relative/path'\n")
    _write(tmp_path / "tests" / "clean.py", "answer = 42\n")
    assert _checker.main([str(tmp_path)]) == 0


def test_missing_scan_dirs_returns_zero(tmp_path: Path) -> None:
    assert _checker.main([str(tmp_path)]) == 0


def test_violation_in_package_returns_one(tmp_path: Path) -> None:
    _write(tmp_path / "komin_terminal" / "bad.py", f"cache = '{HOME_ABS}'\n")
    assert _checker.main([str(tmp_path)]) == 1


def test_violation_in_tests_returns_one(tmp_path: Path) -> None:
    _write(tmp_path / "tests" / "bad.py", f"data = '{ROOT_ABS}'\n")
    assert _checker.main([str(tmp_path)]) == 1


def test_users_prefix_detected_with_location(tmp_path: Path) -> None:
    _write(tmp_path / "komin_terminal" / "pkg" / "bad.py", f"p = '{USERS_ABS}'\n")
    violations = _checker.find_violations(tmp_path)
    assert len(violations) == 1
    path, lineno, line = violations[0]
    assert path == tmp_path / "komin_terminal" / "pkg" / "bad.py"
    assert lineno == 1
    assert USERS_ABS in line


def test_multiple_violations_all_reported(tmp_path: Path) -> None:
    content = f"a = '{HOME_ABS}'\nb = '{ROOT_ABS}'\nc = '{USERS_ABS}'\n"
    _write(tmp_path / "komin_terminal" / "bad.py", content)
    violations = _checker.find_violations(tmp_path)
    assert [lineno for _, lineno, _ in violations] == [1, 2, 3]
