"""
Preferences, kept beside the gestures.

Small enough that a JSON file is the whole story - no need for a registry key
or a config framework.
"""

import json
from pathlib import Path

import gestures

PATH = gestures.STORE.with_name("settings.json")

DEFAULTS = {
    "hotkey": "<ctrl>+<alt>+a",
    "start_minimised": False,
    "start_active": False,
    "close_to_tray": True,
    "check_updates": True,
    "tolerance": 0.22,
    "hold_frames": 8,
    "cooldown": 1.2,
    "margin": 0.33,
    "smoothing": 0.35,
    "scroll_speed": 160.0,
}


def load() -> dict:
    values = dict(DEFAULTS)
    if PATH.exists():
        try:
            values.update(json.loads(PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass                       # a damaged file falls back to defaults

    # The first scroll default was far too gentle to notice. Anyone who never
    # touched the setting gets the new one rather than being stuck with it.
    if values.get("scroll_speed", 0) <= 45.0:
        values["scroll_speed"] = DEFAULTS["scroll_speed"]

    return values


def save(values: dict) -> None:
    try:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        PATH.write_text(json.dumps(values, indent=2), encoding="utf-8")
    except OSError:
        pass


def version() -> str:
    """The installed version, from the VERSION file beside us."""
    f = Path(__file__).resolve().with_name("VERSION")
    try:
        return f.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"
