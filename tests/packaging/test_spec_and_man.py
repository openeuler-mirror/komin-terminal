"""Tests for RPM spec file and man pages."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SPEC_PATH = REPO_ROOT / "packaging" / "komin-terminal.spec"
MAN_DIR = REPO_ROOT / "data" / "release" / "man"
CONFIG_PATH = REPO_ROOT / "data" / "release" / "xdg" / "config.yaml"
DEV_CONFIG_PATH = REPO_ROOT / "data" / "development" / "xdg" / "komin" / "config.yaml"


class TestSpecFile:
    """Tests for packaging/komin-terminal.spec."""

    def test_exists(self) -> None:
        assert SPEC_PATH.is_file()

    def test_contains_three_subpackages(self) -> None:
        content = SPEC_PATH.read_text()
        assert "%package data" in content
        assert "%package doc" in content

    def test_requires_python3(self) -> None:
        content = SPEC_PATH.read_text()
        assert re.search(r"Requires:\s+python3\s*>=\s*3\.11", content)

    def test_requires_dasbus(self) -> None:
        content = SPEC_PATH.read_text()
        assert re.search(r"Requires:\s+python3-dasbus", content)

    def test_requires_httpx(self) -> None:
        content = SPEC_PATH.read_text()
        assert re.search(r"Requires:\s+python3-httpx", content)

    def test_requires_sqlalchemy(self) -> None:
        content = SPEC_PATH.read_text()
        assert re.search(r"Requires:\s+python3-sqlalchemy", content)

    def test_requires_pyyaml(self) -> None:
        content = SPEC_PATH.read_text()
        assert re.search(r"Requires:\s+python3-pyyaml", content)

    def test_build_runs_prepare_release(self) -> None:
        content = SPEC_PATH.read_text()
        assert "prepare_release.py" in content
        assert "--vendor %{_vendor}" in content

    def test_check_runs_make_test(self) -> None:
        content = SPEC_PATH.read_text()
        # Find the %check section and verify it contains make test
        check_match = re.search(r"%check\n(.*?)(?=\n%|\n$|\Z)", content, re.DOTALL)
        assert check_match, "%check section not found"
        assert "make test" in check_match.group(1)

    def test_config_is_noreplace(self) -> None:
        content = SPEC_PATH.read_text()
        assert "%config(noreplace)" in content

    def test_files_data_section_exists(self) -> None:
        content = SPEC_PATH.read_text()
        assert "%files data" in content

    def test_files_doc_section_exists(self) -> None:
        content = SPEC_PATH.read_text()
        assert "%files doc" in content

    def test_post_scriptlet_enables_tmpfiles(self) -> None:
        content = SPEC_PATH.read_text()
        assert "systemd-tmpfiles" in content

    def test_post_scriptlet_reloads_dbus(self) -> None:
        content = SPEC_PATH.read_text()
        assert "busctl daemon-reload" in content


class TestManPages:
    """Tests for man pages."""

    def test_km1_exists(self) -> None:
        assert (MAN_DIR / "km.1").is_file()

    def test_komind8_exists(self) -> None:
        assert (MAN_DIR / "komind.8").is_file()

    def test_km1_has_name_section(self) -> None:
        content = (MAN_DIR / "km.1").read_text()
        assert ".SH NAME" in content

    def test_km1_has_synopsis(self) -> None:
        content = (MAN_DIR / "km.1").read_text()
        assert ".SH SYNOPSIS" in content

    def test_km1_has_description(self) -> None:
        content = (MAN_DIR / "km.1").read_text()
        assert ".SH DESCRIPTION" in content

    def test_km1_has_options(self) -> None:
        content = (MAN_DIR / "km.1").read_text()
        assert ".SH OPTIONS" in content

    def test_km1_has_examples(self) -> None:
        content = (MAN_DIR / "km.1").read_text()
        assert ".SH EXAMPLES" in content

    def test_km1_has_files(self) -> None:
        content = (MAN_DIR / "km.1").read_text()
        assert ".SH FILES" in content

    def test_km1_has_see_also(self) -> None:
        content = (MAN_DIR / "km.1").read_text()
        assert ".SH SEE ALSO" in content

    def test_km1_documents_all_subcommands(self) -> None:
        content = (MAN_DIR / "km.1").read_text()
        assert "chat" in content.lower()
        assert "history" in content.lower()
        assert "shell" in content.lower()

    def test_komind8_has_name_section(self) -> None:
        content = (MAN_DIR / "komind.8").read_text()
        assert ".SH NAME" in content

    def test_komind8_has_synopsis(self) -> None:
        content = (MAN_DIR / "komind.8").read_text()
        assert ".SH SYNOPSIS" in content

    def test_komind8_has_options(self) -> None:
        content = (MAN_DIR / "komind.8").read_text()
        assert ".SH OPTIONS" in content

    def test_komind8_has_files(self) -> None:
        content = (MAN_DIR / "komind.8").read_text()
        assert ".SH FILES" in content

    def test_komind8_has_signals(self) -> None:
        content = (MAN_DIR / "komind.8").read_text()
        assert ".SH SIGNALS" in content

    def test_komind8_has_see_also(self) -> None:
        content = (MAN_DIR / "komind.8").read_text()
        assert ".SH SEE ALSO" in content

    def test_komind8_documents_config_option(self) -> None:
        content = (MAN_DIR / "komind.8").read_text()
        assert "config" in content.lower()

    def test_komind8_documents_debug_option(self) -> None:
        content = (MAN_DIR / "komind.8").read_text()
        assert "debug" in content.lower()

    def test_komind8_documents_version_option(self) -> None:
        content = (MAN_DIR / "komind.8").read_text()
        assert "version" in content.lower()

    def test_man_pages_reference_fhs_paths(self) -> None:
        km1 = (MAN_DIR / "km.1").read_text()
        komind8 = (MAN_DIR / "komind.8").read_text()
        for path in ("/etc/komin", "/var/lib/komin"):
            assert path in km1, f"{path} not referenced in km.1"
            assert path in komind8, f"{path} not referenced in komind.8"


class TestExampleConfig:
    """Tests for the release example config file."""

    def test_exists(self) -> None:
        assert CONFIG_PATH.is_file()

    def test_is_valid_yaml(self) -> None:
        raw = yaml.safe_load(CONFIG_PATH.read_text())
        assert isinstance(raw, dict)

    def test_has_required_sections(self) -> None:
        raw = yaml.safe_load(CONFIG_PATH.read_text())
        for section in ("backend", "database", "display", "logging"):
            assert section in raw, f"Missing section: {section}"

    def test_backend_has_required_fields(self) -> None:
        raw = yaml.safe_load(CONFIG_PATH.read_text())
        backend = raw["backend"]
        for field in ("url", "api_key", "model"):
            assert field in backend, f"Missing backend.{field}"

    def test_api_key_is_placeholder(self) -> None:
        raw = yaml.safe_load(CONFIG_PATH.read_text())
        assert raw["backend"]["api_key"] == "sk-REPLACE-ME"

    def test_database_sqlite_path(self) -> None:
        raw = yaml.safe_load(CONFIG_PATH.read_text())
        assert raw["database"]["type"] == "sqlite"
        assert "path" in raw["database"].get("sqlite", {})


class TestDevExampleConfig:
    """Tests for the development example config file."""

    def test_exists(self) -> None:
        assert DEV_CONFIG_PATH.is_file()

    def test_is_valid_yaml(self) -> None:
        raw = yaml.safe_load(DEV_CONFIG_PATH.read_text())
        assert isinstance(raw, dict)

    def test_has_required_sections(self) -> None:
        raw = yaml.safe_load(DEV_CONFIG_PATH.read_text())
        for section in ("backend", "database", "display", "logging"):
            assert section in raw, f"Missing section: {section}"

    def test_api_key_is_placeholder(self) -> None:
        raw = yaml.safe_load(DEV_CONFIG_PATH.read_text())
        assert raw["backend"]["api_key"] == "sk-REPLACE-ME"
