"""Tests for systemd and tmpfiles deployment files."""

from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RELEASE_DIR = REPO_ROOT / "data" / "release" / "systemd"
DEVEL_DIR = REPO_ROOT / "data" / "development" / "systemd"


def _read_service(path: Path) -> ConfigParser:
    """Parse a systemd .service file into a ConfigParser."""
    cp = ConfigParser()
    cp.read(path, encoding="utf-8")
    return cp


class TestKomindService:
    """Tests for data/release/systemd/komind.service."""

    def test_exists(self) -> None:
        assert (RELEASE_DIR / "komind.service").is_file()

    def test_type_is_dbus(self) -> None:
        cp = _read_service(RELEASE_DIR / "komind.service")
        assert cp.get("Service", "Type") == "dbus"

    def test_bus_name_has_vendor_placeholder(self) -> None:
        cp = _read_service(RELEASE_DIR / "komind.service")
        bus_name = cp.get("Service", "BusName")
        assert "{vendor}" in bus_name, f"BusName must contain {{vendor}}: {bus_name}"

    def test_exec_start_is_komind(self) -> None:
        cp = _read_service(RELEASE_DIR / "komind.service")
        assert cp.get("Service", "ExecStart") == "/usr/bin/komind"

    def test_restart_on_failure(self) -> None:
        cp = _read_service(RELEASE_DIR / "komind.service")
        assert cp.get("Service", "Restart") == "on-failure"

    def test_wanted_by_multi_user(self) -> None:
        cp = _read_service(RELEASE_DIR / "komind.service")
        assert cp.get("Install", "WantedBy") == "multi-user.target"

    def test_after_network_online(self) -> None:
        cp = _read_service(RELEASE_DIR / "komind.service")
        assert "network-online.target" in cp.get("Unit", "After", fallback="")

    def test_no_hardcoded_paths(self) -> None:
        content = (RELEASE_DIR / "komind.service").read_text()
        for prefix in ("/home/", "/root/", "/Users/"):
            assert prefix not in content, f"Forbidden path {prefix} in komind.service"


class TestTmpfilesConf:
    """Tests for data/release/systemd/komind.tmpfiles.conf."""

    def test_exists(self) -> None:
        assert (RELEASE_DIR / "komind.tmpfiles.conf").is_file()

    def test_creates_var_lib_komin(self) -> None:
        content = (RELEASE_DIR / "komind.tmpfiles.conf").read_text().strip()
        assert "/var/lib/komin" in content

    def test_sets_permissions(self) -> None:
        content = (RELEASE_DIR / "komind.tmpfiles.conf").read_text().strip()
        assert "0750" in content

    def test_sets_owner(self) -> None:
        content = (RELEASE_DIR / "komind.tmpfiles.conf").read_text().strip()
        assert "root root" in content


class TestDevelService:
    """Tests for data/development/systemd/komind-devel.service."""

    def test_exists(self) -> None:
        assert (DEVEL_DIR / "komind-devel.service").is_file()

    def test_vendor_env_set_to_example(self) -> None:
        cp = _read_service(DEVEL_DIR / "komind-devel.service")
        env = cp.get("Service", "Environment", fallback="")
        assert "KOMIN_DBUS_VENDOR=example" in env

    def test_type_is_dbus(self) -> None:
        cp = _read_service(DEVEL_DIR / "komind-devel.service")
        assert cp.get("Service", "Type") == "dbus"

    def test_bus_name_has_vendor_placeholder(self) -> None:
        cp = _read_service(DEVEL_DIR / "komind-devel.service")
        bus_name = cp.get("Service", "BusName")
        assert "{vendor}" in bus_name


class TestConsistency:
    """Path consistency between deployment files and constants."""

    def test_service_exec_start_is_fhs_path(self) -> None:
        content = (RELEASE_DIR / "komind.service").read_text()
        assert "/usr/bin/komind" in content

    def test_tmpfiles_path_matches_sqlite_default_dir(self) -> None:
        from komin_terminal.constants import SQLITE_DEFAULT_PATH

        tmpfiles_content = (RELEASE_DIR / "komind.tmpfiles.conf").read_text()
        # The tmpfiles line should create the directory containing the DB.
        assert str(SQLITE_DEFAULT_PATH.parent) in tmpfiles_content
