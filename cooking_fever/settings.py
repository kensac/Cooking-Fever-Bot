"""Persisted dashboard preferences (separate from restaurant profiles).

Remembers the user's last selections - which profile was active, the template
matching confidence, and the dry-run toggle - so the dashboard reopens the way
it was left. Stored as settings.json beside the app.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from . import paths

_DEFAULTS: Dict[str, Any] = {
    "last_profile_path": "",
    "confidence": 0.8,
    "dry_run": False,
}


def _settings_path() -> Path:
    return paths.APP_DIRECTORY / "settings.json"


def load() -> Dict[str, Any]:
    settings = dict(_DEFAULTS)
    path = _settings_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                settings.update({k: data[k] for k in _DEFAULTS if k in data})
        except (OSError, ValueError):
            pass
    return settings


def save(settings: Dict[str, Any]) -> None:
    merged = dict(_DEFAULTS)
    merged.update({k: settings[k] for k in _DEFAULTS if k in settings})
    try:
        _settings_path().write_text(json.dumps(merged, indent=2), encoding="utf-8")
    except OSError:
        pass
