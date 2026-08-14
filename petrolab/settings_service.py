from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from petrolab.db import DATA_DIR


SETTINGS_PATH = Path(DATA_DIR) / "settings.json"
DEFAULT_SETTINGS: dict[str, Any] = {
    "default_figure_preset": "Lithos",
    "default_table_preset": "Lithos",
    "default_point_style": "balanced",
    "ui_density": "comfortable",
    "show_help_hints": True,
    "show_sample_location_prompt": True,
    "show_release_notes_on_home": True,
    "check_updates_automatically": True,
    "default_outlier_method": "MAD",
    "default_ree_reference": "CI-хондрит · McDonough & Sun (1995)",
}


def load_settings() -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    if not SETTINGS_PATH.exists():
        return settings
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return settings
    if isinstance(raw, dict):
        settings.update(raw)
    return settings


def save_settings(settings: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    merged = dict(DEFAULT_SETTINGS)
    merged.update(settings)
    temporary = SETTINGS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(SETTINGS_PATH)
