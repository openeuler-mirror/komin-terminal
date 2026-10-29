"""Tests for scripts/prepare_release.py vendor substitution."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "prepare_release.py"


@pytest.fixture()
def vendor_tree(tmp_path: Path) -> Path:
    """Create a minimal file tree with {vendor} placeholders."""
    # Text files with placeholders
    (tmp_path / "service.conf").write_text("BusName=com.{vendor}.komin\n")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "policy.xml").write_text(
        '<allow own="com.{vendor}.komin"/>\n'
    )
    # Text file without placeholders
    (tmp_path / "readme.txt").write_text("No placeholder here.\n")
    # Binary file (should be skipped)
    (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02{vendor}\x03")
    return tmp_path


class TestSubstituteVendor:
    """Unit tests for the substitute_vendor function."""

    def test_replaces_in_text_files(self, vendor_tree: Path) -> None:
        from scripts.prepare_release import substitute_vendor

        modified = substitute_vendor(vendor_tree, "acme")
        assert len(modified) >= 2
        assert "com.acme.komin" in (vendor_tree / "service.conf").read_text()
        assert "com.acme.komin" in (vendor_tree / "nested" / "policy.xml").read_text()

    def test_skips_binary_files(self, vendor_tree: Path) -> None:
        from scripts.prepare_release import substitute_vendor

        modified = substitute_vendor(vendor_tree, "acme")
        binary_in_modified = any(p.name == "binary.bin" for p in modified)
        assert not binary_in_modified, "Binary files must be skipped"

    def test_skips_clean_files(self, vendor_tree: Path) -> None:
        from scripts.prepare_release import substitute_vendor

        modified = substitute_vendor(vendor_tree, "acme")
        clean_in_modified = any(p.name == "readme.txt" for p in modified)
        assert not clean_in_modified, "Files without {vendor} must be skipped"

    def test_returns_modified_paths(self, vendor_tree: Path) -> None:
        from scripts.prepare_release import substitute_vendor

        modified = substitute_vendor(vendor_tree, "acme")
        for p in modified:
            assert p.is_file()

    def test_dry_run_does_not_write(self, vendor_tree: Path) -> None:
        from scripts.prepare_release import substitute_vendor

        original = (vendor_tree / "service.conf").read_text()
        modified = substitute_vendor(vendor_tree, "acme", dry_run=True)
        assert len(modified) >= 1
        assert (vendor_tree / "service.conf").read_text() == original

    def test_idempotent(self, vendor_tree: Path) -> None:
        from scripts.prepare_release import substitute_vendor

        substitute_vendor(vendor_tree, "acme")
        second_run = substitute_vendor(vendor_tree, "acme")
        assert len(second_run) == 0, "Second run should find no remaining {vendor}"

    def test_empty_dir(self, tmp_path: Path) -> None:
        from scripts.prepare_release import substitute_vendor

        modified = substitute_vendor(tmp_path, "acme")
        assert modified == []


class TestVendorValidation:
    """Tests for vendor name validation."""

    @pytest.mark.parametrize(
        "vendor",
        ["acme", "my-company", "vendor123", "a", "123"],
    )
    def test_valid_vendors(self, vendor: str) -> None:
        from scripts.prepare_release import _validate_vendor

        assert _validate_vendor(vendor), f"Expected valid: {vendor}"

    @pytest.mark.parametrize(
        "vendor",
        ["ACME", "My-Company", "has space", "-leading", "trailing-", "_underscore"],
    )
    def test_invalid_vendors(self, vendor: str) -> None:
        from scripts.prepare_release import _validate_vendor

        assert not _validate_vendor(vendor), f"Expected invalid: {vendor}"


class TestCLI:
    """Integration tests for the CLI entry point."""

    def test_help_returns_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_missing_vendor_returns_nonzero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "--vendor" in result.stderr

    def test_invalid_vendor_returns_nonzero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--vendor", "INVALID_VENDOR"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "invalid" in result.stderr.lower()

    def test_dry_run_with_vendor(self, tmp_path: Path) -> None:
        (tmp_path / "test.conf").write_text("com.{vendor}.komin\n")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(tmp_path), "--vendor", "acme", "--dry-run"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Would modify" in result.stdout
        # File should NOT be modified
        assert "{vendor}" in (tmp_path / "test.conf").read_text()
