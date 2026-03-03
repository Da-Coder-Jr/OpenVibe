from __future__ import annotations

import json
from pathlib import Path
from typing import Any

APP_HOME = Path.home() / ".openv"
CONFIG_PATH = APP_HOME / "config.json"
LOG_DIR = APP_HOME / "logs"
TRACE_PATH = LOG_DIR / "trace.json"
DB_PATH = APP_HOME / "vault.db"

DEFAULT_CONFIG: dict[str, Any] = {
    "ollama": {
        "base_url": "http://127.0.0.1:11434",
        "model": "llama3.1",
        "timeout": 90,
    },
    "ui": {
        "stream_panel_title": "OpenV • The Weave",
    },
}


def ensure_app_dirs() -> None:
    APP_HOME.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    ensure_app_dirs()
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
        raw = json.load(config_file)

    merged = DEFAULT_CONFIG.copy()
    for key, value in raw.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            base = dict(merged[key])
            base.update(value)
            merged[key] = base
        else:
            merged[key] = value
    return merged


def save_config(config: dict[str, Any]) -> None:
    ensure_app_dirs()
    with CONFIG_PATH.open("w", encoding="utf-8") as config_file:
        json.dump(config, config_file, indent=2, sort_keys=True)
