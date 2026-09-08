"""UI strings (en/fr/es). Game names live in data/game_names.json."""

from __future__ import annotations

import json
import os

from .paths import resource_root

SUPPORTED = ("en", "fr", "es")
_DIR = resource_root() / "scandeck" / "locales"
_DATA = resource_root() / "data" / "game_names.json"

_lang = "en"
_auto = True
_ui: dict[str, dict[str, str]] = {}
_game: dict[str, dict[str, dict[str, str]]] = {}


def _load() -> None:
    global _ui, _game
    if _ui:
        return
    for code in SUPPORTED:
        path = _DIR / f"{code}.json"
        _ui[code] = json.loads(path.read_text(encoding="utf-8"))
    if _DATA.exists():
        _game = json.loads(_DATA.read_text(encoding="utf-8"))


def lang() -> str:
    _load()
    return _lang


def is_auto() -> bool:
    return _auto


def set_lang(code: str, *, auto: bool | None = None) -> None:
    global _lang, _auto
    _load()
    raw = (code or "en").lower().replace("_", "-")
    if raw.startswith("fr"):
        _lang = "fr"
    elif raw.startswith("es") or raw.startswith("sp"):
        _lang = "es"
    else:
        _lang = "en"
    if auto is not None:
        _auto = auto


def apply_fileheader(language: str | None) -> None:
    """Fileheader.language looks like 'French/FR'."""
    if not _auto or not language:
        return
    set_lang(language.split("/", 1)[0], auto=True)


def t(key: str, **kwargs) -> str:
    _load()
    text = _ui.get(_lang, {}).get(key) or _ui["en"].get(key) or key
    if kwargs:
        return text.format(**kwargs)
    return text


def game_name(kind: str, english_key: str | None) -> str:
    """Official in-game label for a catalog/journal English key."""
    _load()
    if not english_key:
        return ""
    row = (_game.get(kind) or {}).get(english_key)
    if not row:
        return english_key
    return row.get(_lang) or row.get("en") or english_key


def decimal_sep() -> str:
    return "." if _lang == "en" else ","


def init_from_env(explicit: str | None = None) -> None:
    if explicit and explicit != "auto":
        set_lang(explicit, auto=False)
        return
    env = os.environ.get("SCANDECK_LANG") or os.environ.get("LANG") or "en"
    set_lang(env, auto=True)
