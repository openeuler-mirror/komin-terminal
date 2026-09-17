"""Tests for komin_terminal.utils.files."""

from __future__ import annotations

import stat
import threading
from pathlib import Path

from komin_terminal.exceptions import KominError
from komin_terminal.utils.files import locked_file, write_atomic


def test_locked_file_read_write_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "data.txt"
    with locked_file(target, "w") as handle:
        handle.write("hello komin")
    with locked_file(target, "r") as handle:
        assert handle.read() == "hello komin"


def test_locked_file_mutual_exclusion(tmp_path: Path) -> None:
    target = tmp_path / "locked.txt"
    target.write_text("payload", encoding="utf-8")
    acquired = threading.Event()
    release = threading.Event()
    outcomes: list[str] = []

    def holder() -> None:
        with locked_file(target, "r", timeout=5.0):
            acquired.set()
            release.wait(timeout=10.0)

    def contender() -> None:
        try:
            with locked_file(target, "r", timeout=0.3):
                outcomes.append("acquired")
        except KominError:
            outcomes.append("timeout")

    holder_thread = threading.Thread(target=holder)
    holder_thread.start()
    assert acquired.wait(timeout=5.0)

    contender_thread = threading.Thread(target=contender)
    contender_thread.start()
    contender_thread.join(timeout=10.0)

    release.set()
    holder_thread.join(timeout=5.0)
    assert outcomes == ["timeout"]


def test_locked_file_released_after_context(tmp_path: Path) -> None:
    target = tmp_path / "released.txt"
    target.write_text("payload", encoding="utf-8")
    with locked_file(target, "r"):
        pass
    with locked_file(target, "r", timeout=0.5) as handle:
        assert handle.read() == "payload"


def test_write_atomic_content_and_default_permissions(tmp_path: Path) -> None:
    target = tmp_path / "atomic.txt"
    write_atomic(target, "new content")
    assert target.read_text(encoding="utf-8") == "new content"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_write_atomic_custom_mode(tmp_path: Path) -> None:
    target = tmp_path / "custom-mode.txt"
    write_atomic(target, "data", mode=0o644)
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


def test_write_atomic_replaces_existing_content(tmp_path: Path) -> None:
    target = tmp_path / "replace.txt"
    target.write_text("old", encoding="utf-8")
    write_atomic(target, "new")
    assert target.read_text(encoding="utf-8") == "new"


def test_write_atomic_readers_only_see_complete_content(tmp_path: Path) -> None:
    target = tmp_path / "race.txt"
    old_content = "a" * 100_000
    new_content = "b" * 100_000
    target.write_text(old_content, encoding="utf-8")

    stop = threading.Event()
    observations: set[str] = set()

    def reader() -> None:
        while not stop.is_set():
            try:
                observations.add(target.read_text(encoding="utf-8"))
            except FileNotFoundError:
                observations.add("<missing>")

    reader_thread = threading.Thread(target=reader)
    reader_thread.start()
    for _ in range(25):
        write_atomic(target, new_content)
        write_atomic(target, old_content)
    stop.set()
    reader_thread.join(timeout=10.0)

    assert "<missing>" not in observations
    assert observations <= {old_content, new_content}


def test_write_atomic_no_leftover_temp_files(tmp_path: Path) -> None:
    target = tmp_path / "clean.txt"
    write_atomic(target, "content")
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["clean.txt"]
