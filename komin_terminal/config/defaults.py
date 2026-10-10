"""Built-in configuration defaults and deep-merge helper.

:data:`DEFAULTS` mirrors the YAML configuration format. Required fields
(``backend.url``, ``backend.api_key``, ``backend.model``) intentionally have
no defaults and must come from a configuration file or CLI overrides.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

DEFAULTS: Mapping[str, Any] = {
    "backend": {
        "timeout": 120,
        "max_retries": 3,
    },
    "database": {
        "type": "sqlite",
        "host": "localhost",
        "name": "komin",
        "user": "komin",
    },
    "display": {
        "theme": "default",
        "spinner": True,
        "max_width": 0,
    },
    "logging": {
        "level": "info",
        "audit": True,
    },
}


def merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Deep-merge ``override`` on top of ``base``.

    Nested mappings are merged recursively; scalars and lists from
    ``override`` replace the ``base`` value wholesale. Neither input is
    mutated and the returned tree shares no mutable state with them.

    Args:
        base: Lower-precedence mapping (e.g. defaults or a system file).
        override: Higher-precedence mapping whose values win on conflict.

    Returns:
        A new, fully independent mapping containing the merged result.
    """
    merged: dict[str, Any] = {}
    for key, base_value in base.items():
        if key not in override:
            merged[key] = copy.deepcopy(base_value)
            continue
        override_value = override[key]
        if isinstance(base_value, Mapping) and isinstance(override_value, Mapping):
            merged[key] = merge(base_value, override_value)
        else:
            merged[key] = copy.deepcopy(override_value)
    for key, override_value in override.items():
        if key not in base:
            merged[key] = copy.deepcopy(override_value)
    return merged
