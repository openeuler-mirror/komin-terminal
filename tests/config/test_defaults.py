"""Tests for komin_terminal.config.defaults."""

from __future__ import annotations

import copy
from typing import Any

from komin_terminal.config.defaults import DEFAULTS, merge


def test_defaults_contain_documented_values() -> None:
    assert DEFAULTS["backend"]["timeout"] == 120
    assert DEFAULTS["backend"]["max_retries"] == 3
    assert DEFAULTS["database"]["type"] == "sqlite"
    assert DEFAULTS["display"] == {"theme": "default", "spinner": True, "max_width": 0}
    assert DEFAULTS["logging"] == {"level": "info", "audit": True}


def test_defaults_have_no_required_backend_fields() -> None:
    backend = DEFAULTS["backend"]
    assert "api_key" not in backend
    assert "url" not in backend
    assert "model" not in backend


def test_merge_recurses_into_nested_dicts() -> None:
    base: dict[str, Any] = {
        "backend": {"timeout": 120, "max_retries": 3},
        "logging": {"level": "info"},
    }
    override: dict[str, Any] = {"backend": {"timeout": 30}}
    merged = merge(base, override)
    assert merged == {
        "backend": {"timeout": 30, "max_retries": 3},
        "logging": {"level": "info"},
    }


def test_merge_replaces_lists_wholesale() -> None:
    base: dict[str, Any] = {"backend": {"models": ["a", "b", "c"]}}
    override: dict[str, Any] = {"backend": {"models": ["z"]}}
    merged = merge(base, override)
    assert merged["backend"]["models"] == ["z"]


def test_merge_override_wins_on_scalars() -> None:
    base: dict[str, Any] = {"display": {"spinner": True, "max_width": 0}}
    override: dict[str, Any] = {"display": {"spinner": False}}
    merged = merge(base, override)
    assert merged["display"]["spinner"] is False
    assert merged["display"]["max_width"] == 0


def test_merge_keeps_keys_only_in_base() -> None:
    base: dict[str, Any] = {"backend": {"timeout": 120}}
    override: dict[str, Any] = {"logging": {"level": "debug"}}
    merged = merge(base, override)
    assert merged == {"backend": {"timeout": 120}, "logging": {"level": "debug"}}


def test_merge_does_not_mutate_inputs() -> None:
    base: dict[str, Any] = {"backend": {"timeout": 120, "models": ["a"]}}
    override: dict[str, Any] = {"backend": {"timeout": 30}}
    base_snapshot = copy.deepcopy(base)
    override_snapshot = copy.deepcopy(override)
    merge(base, override)
    assert base == base_snapshot
    assert override == override_snapshot


def test_merge_result_is_independent_of_inputs() -> None:
    base: dict[str, Any] = {"backend": {"timeout": 120, "models": ["a"]}}
    override: dict[str, Any] = {"backend": {"proxy": {"http": "http://proxy"}}}
    merged = merge(base, override)
    merged["backend"]["timeout"] = 999
    merged["backend"]["models"].append("mutated")
    merged["backend"]["proxy"]["http"] = "mutated"
    assert base["backend"]["timeout"] == 120
    assert base["backend"]["models"] == ["a"]
    assert override["backend"]["proxy"]["http"] == "http://proxy"


def test_merge_with_empty_override_copies_base() -> None:
    base: dict[str, Any] = {"backend": {"timeout": 120}}
    merged = merge(base, {})
    assert merged == base
    assert merged is not base


def test_merge_with_empty_base_copies_override() -> None:
    override: dict[str, Any] = {"backend": {"url": "https://api.example.com"}}
    merged = merge({}, override)
    assert merged == override
    assert merged is not override
