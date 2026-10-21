"""Import-safety tests: the bus module must work without pygobject."""

from __future__ import annotations

import importlib
import sys

import pytest
from komin_terminal.exceptions import DBusCommunicationError


def test_bus_module_imports_without_pygobject(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "dasbus", None)
    monkeypatch.setitem(sys.modules, "gi", None)
    monkeypatch.delitem(sys.modules, "komin_terminal.dbus.bus")

    module = importlib.import_module("komin_terminal.dbus.bus")

    with pytest.raises(DBusCommunicationError):
        module.SystemBusBackend()
