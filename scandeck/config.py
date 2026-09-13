"""User settings (language, journal folder) next to the workbook."""

from __future__ import annotations

import json
import os
from pathlib import Path

_DEFAULTS = {
    "lang": "auto",
    "journal_dir": "",
    "eddn_enabled": True,
    "inara_api_key": "",
}


def user_data_dir() -> Path:
    if os.name == "nt":
        base = Path.home() / "Documents" / "ScanDeck"
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg) / "ScanDeck" if xdg else Path.home() / ".local/share/ScanDeck"
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_path() -> Path:
    return user_data_dir() / "config.json"


def load() -> dict:
    path = config_path()
    if not path.exists():
        return dict(_DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(_DEFAULTS)
    out = dict(_DEFAULTS)
    if data.get("lang") in {"auto", "en", "fr", "es"}:
        out["lang"] = data["lang"]
    folder = data.get("journal_dir")
    if isinstance(folder, str):
        out["journal_dir"] = folder.strip()
    if isinstance(data.get("eddn_enabled"), bool):
        out["eddn_enabled"] = data["eddn_enabled"]
    key = data.get("inara_api_key")
    if isinstance(key, str):
        out["inara_api_key"] = key.strip()
    return out


def save(data: dict) -> None:
    payload = load()
    for k in _DEFAULTS:
        if k in data:
            payload[k] = data[k]
    config_path().write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
