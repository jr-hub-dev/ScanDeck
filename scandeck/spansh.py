"""Public-map lookup: is this system already on Spansh (EDDN)?

One GET to /api/system/{id64}. EDSM is a fallback only when Spansh errors
(not when it 404s). Never call /dump — too heavy for a HUD tag.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

SPANSH_URL = "https://spansh.co.uk/api/system/{addr}"
EDSM_URL = "https://www.edsm.net/api-v1/system"
TIMEOUT_S = 3
_UA = {"User-Agent": f"ScanDeck/{__version__}"}


def system_on_public_map(address: int, name: str = "") -> bool | None:
    """True = listed, False = not listed, None = network/error (try later)."""
    hit = _spansh(address)
    if hit is not None:
        return hit
    if name.strip():
        return _edsm(name.strip())
    return None


def _spansh(address: int) -> bool | None:
    req = urllib.request.Request(SPANSH_URL.format(addr=int(address)), headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            if getattr(resp, "status", 200) == 200:
                return True
            return None
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        return None
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def _edsm(name: str) -> bool | None:
    qs = urllib.parse.urlencode({"systemName": name, "showId": 1})
    req = urllib.request.Request(f"{EDSM_URL}?{qs}", headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError, urllib.error.HTTPError):
        return None
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and data.get("name"):
        return True
    return False
