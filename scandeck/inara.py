"""Manual Inara profile push (API key in Options).

appName stays 'ScanDeck' (whitelisted by Artie). Commander, system, and
ranks come from the EDDN hub (journal LoadGame / location / Progress).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

from . import __version__
from .config import load as load_config, user_data_dir
from .eddn import get_hub

INARA_URL = "https://inara.cz/inapi/v1/"

# Inara replies (header.eventStatusText) → HUD codes.
_STATUS_CODES = {
    "this application has no access allowed": "app_blocked",
    "this application is not allowed to use inara api": "app_blocked",
    "invalid api key": "bad_key",
    "api key is not valid": "bad_key",
    "wrong api key": "bad_key",
    "api key not found": "bad_key",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sync() -> dict:
    """POST travel location + explore/exo ranks. Returns {ok, detail}."""
    cfg = load_config()
    key = (cfg.get("inara_api_key") or "").strip()
    if not key:
        return {"ok": False, "detail": "missing_key"}
    hub = get_hub()
    if not hub.cmdr:
        return {"ok": False, "detail": "no_cmdr"}
    events: list[dict] = []
    loc: dict = {}
    if hub.system:
        loc["starsystemName"] = hub.system
    if hub.starpos:
        loc["starsystemCoords"] = list(hub.starpos)
    if hub.body:
        loc["starsystemBodyName"] = hub.body
    if loc.get("starsystemName"):
        events.append({
            "eventName": "setCommanderTravelLocation",
            "eventTimestamp": _now(),
            "eventData": loc,
        })
    ranks = []
    if hub.explore_rank is not None:
        row = {"rankName": "explore", "rankValue": hub.explore_rank}
        if hub.explore_progress is not None:
            row["rankProgress"] = max(0.0, min(1.0, hub.explore_progress / 100.0))
        ranks.append(row)
    if hub.exo_rank is not None:
        row = {"rankName": "exobiologist", "rankValue": hub.exo_rank}
        if hub.exo_progress is not None:
            row["rankProgress"] = max(0.0, min(1.0, hub.exo_progress / 100.0))
        ranks.append(row)
    if ranks:
        events.append({
            "eventName": "setCommanderRankPilot",
            "eventTimestamp": _now(),
            "eventData": ranks,
        })
    if not events:
        return {"ok": False, "detail": "nothing"}
    header = {
        "appName": "ScanDeck",
        "appVersion": __version__,
        "isBeingDeveloped": False,
        "APIkey": key,
        "commanderName": hub.cmdr,
    }
    if hub.fid:
        header["commanderFrontierID"] = hub.fid
    payload = {"header": header, "events": events}
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        INARA_URL,
        data=raw,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"ScanDeck/{__version__}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            code = getattr(resp, "status", 200)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        return _finish(False, body, exc.code, key)
    except urllib.error.URLError as exc:
        return {"ok": False, "detail": "network", "reason": str(exc.reason or exc)}
    return _finish(code == 200, body, code, key)


def _status_text(parsed: dict, body: str) -> str:
    header = parsed.get("header") or {}
    text = str(header.get("eventStatusText") or "").strip()
    if text:
        return text
    for event in parsed.get("events") or []:
        if not isinstance(event, dict):
            continue
        text = str(event.get("eventStatusText") or "").strip()
        if text:
            return text
    low = body.lower()
    if "<html" in low or "access check" in low:
        return "blocked_html"
    return ""


def _detail_code(text: str) -> str:
    return _STATUS_CODES.get(text.lower().strip().rstrip(".")) or "api"


def _redact(text: str, key: str) -> str:
    if key and key in text:
        return text.replace(key, "…")
    return text


def _finish(http_ok: bool, body: str, code: int, key: str) -> dict:
    try:
        parsed = json.loads(body) if body else {}
    except json.JSONDecodeError:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    header_status = (parsed.get("header") or {}).get("eventStatus")
    text = _status_text(parsed, body)
    ok = http_ok and header_status in (None, 200, 202)
    if ok:
        detail = "ok"
    elif text == "blocked_html":
        detail = "blocked_html"
        text = ""
    elif text:
        detail = _detail_code(text)
    elif not http_ok:
        detail = "http"
        text = f"HTTP {code}"
    else:
        detail = "api"
        text = f"HTTP {code}" if code else "unknown"
    result = {
        "ok": bool(ok),
        "code": code,
        "detail": detail,
        "status": header_status,
        "reason": _redact(text, key)[:200],
    }
    try:
        log = {
            "ok": result["ok"],
            "code": code,
            "detail": detail,
            "status": header_status,
            "reason": result["reason"],
        }
        (user_data_dir() / "inara.log").write_text(
            json.dumps(log, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    return result
