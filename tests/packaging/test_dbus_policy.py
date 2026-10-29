"""Tests for D-Bus policy and activation files."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RELEASE_DBUS = REPO_ROOT / "data" / "release" / "dbus"
DEVEL_DBUS = REPO_ROOT / "data" / "development" / "dbus"

_ACTIVATION_SERVICES = ("chat", "history", "user")


def _parse_xml(path: Path) -> ET.Element:
    """Parse an XML file and return the root element."""
    return ET.parse(path).getroot()  # noqa: S314


class TestBusPolicyXml:
    """Tests for com.{vendor}.komin.conf D-Bus policy."""

    def test_exists(self) -> None:
        assert (RELEASE_DBUS / "com.{vendor}.komin.conf").is_file()

    def test_is_well_formed_xml(self) -> None:
        root = _parse_xml(RELEASE_DBUS / "com.{vendor}.komin.conf")
        assert root.tag == "busconfig"

    def test_root_policy_has_own(self) -> None:
        root = _parse_xml(RELEASE_DBUS / "com.{vendor}.komin.conf")
        for policy in root.findall("policy"):
            if policy.get("user") == "root":
                has_own = any(a.get("own") is not None for a in policy.findall("allow"))
                assert has_own, "root policy must allow own"
                return
        pytest.fail("No root policy found")

    def test_root_policy_has_send_destination(self) -> None:
        root = _parse_xml(RELEASE_DBUS / "com.{vendor}.komin.conf")
        for policy in root.findall("policy"):
            if policy.get("user") == "root":
                has_send = any(
                    a.get("send_destination") is not None for a in policy.findall("allow")
                )
                assert has_send, "root policy must allow send_destination"
                return
        pytest.fail("No root policy found")

    def test_root_policy_has_receive_sender(self) -> None:
        root = _parse_xml(RELEASE_DBUS / "com.{vendor}.komin.conf")
        for policy in root.findall("policy"):
            if policy.get("user") == "root":
                has_recv = any(
                    a.get("receive_sender") is not None for a in policy.findall("allow")
                )
                assert has_recv, "root policy must allow receive_sender"
                return
        pytest.fail("No root policy found")

    def test_default_policy_allows_three_services(self) -> None:
        root = _parse_xml(RELEASE_DBUS / "com.{vendor}.komin.conf")
        for policy in root.findall("policy"):
            if policy.get("context") == "default":
                destinations = set()
                for allow in policy.findall("allow"):
                    dest = allow.get("send_destination", "")
                    if "komin." in dest:
                        # Extract the service suffix (chat/history/user)
                        suffix = dest.rsplit(".", 1)[-1]
                        destinations.add(suffix)
                assert destinations == set(
                    _ACTIVATION_SERVICES
                ), f"Expected {_ACTIVATION_SERVICES}, got {destinations}"
                return
        pytest.fail("No default policy found")

    def test_default_policy_no_own(self) -> None:
        root = _parse_xml(RELEASE_DBUS / "com.{vendor}.komin.conf")
        for policy in root.findall("policy"):
            if policy.get("context") == "default":
                has_own = any(a.get("own") is not None for a in policy.findall("allow"))
                assert not has_own, "default policy must not allow own"
                return
        pytest.fail("No default policy found")

    def test_policy_has_vendor_placeholder(self) -> None:
        content = (RELEASE_DBUS / "com.{vendor}.komin.conf").read_text()
        assert "{vendor}" in content


class TestActivationFiles:
    """Tests for D-Bus activation service files."""

    @pytest.mark.parametrize("service", _ACTIVATION_SERVICES)
    def test_file_exists(self, service: str) -> None:
        path = RELEASE_DBUS / f"com.{{vendor}}.komin.{service}.service"
        assert path.is_file(), f"Activation file missing: {path.name}"

    @pytest.mark.parametrize("service", _ACTIVATION_SERVICES)
    def test_is_ini_format(self, service: str) -> None:
        path = RELEASE_DBUS / f"com.{{vendor}}.komin.{service}.service"
        content = path.read_text()
        assert "[D-BUS Service]" in content

    @pytest.mark.parametrize("service", _ACTIVATION_SERVICES)
    def test_name_matches_template(self, service: str) -> None:
        path = RELEASE_DBUS / f"com.{{vendor}}.komin.{service}.service"
        content = path.read_text()
        assert f"Name=com.{{vendor}}.komin.{service}" in content

    @pytest.mark.parametrize("service", _ACTIVATION_SERVICES)
    def test_exec_is_komind(self, service: str) -> None:
        path = RELEASE_DBUS / f"com.{{vendor}}.komin.{service}.service"
        content = path.read_text()
        assert "Exec=/usr/bin/komind" in content

    @pytest.mark.parametrize("service", _ACTIVATION_SERVICES)
    def test_user_is_root(self, service: str) -> None:
        path = RELEASE_DBUS / f"com.{{vendor}}.komin.{service}.service"
        content = path.read_text()
        assert "User=root" in content

    @pytest.mark.parametrize("service", _ACTIVATION_SERVICES)
    def test_has_vendor_placeholder(self, service: str) -> None:
        path = RELEASE_DBUS / f"com.{{vendor}}.komin.{service}.service"
        content = path.read_text()
        assert "{vendor}" in content


class TestDevelBusPolicy:
    """Tests for development D-Bus policy file."""

    def test_exists(self) -> None:
        assert (DEVEL_DBUS / "com.{vendor}.komin.conf").is_file()

    def test_is_well_formed_xml(self) -> None:
        root = _parse_xml(DEVEL_DBUS / "com.{vendor}.komin.conf")
        assert root.tag == "busconfig"

    def test_has_vendor_placeholder(self) -> None:
        content = (DEVEL_DBUS / "com.{vendor}.komin.conf").read_text()
        assert "{vendor}" in content
