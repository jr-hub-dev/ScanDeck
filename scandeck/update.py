"""Check GitHub Releases for a newer ScanDeck (no token, fail silent)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import __version__

REPO = "jr-hub-dev/ScanDeck"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"


def _parse(ver: str) -> tuple[int, ...]:
    ver = ver.strip().lstrip("vV")
    out: list[int] = []
    for part in ver.split("."):
        digits = ""
        for ch in part:
            if ch.isdigit():
                digits += ch
            else:
                break
        out.append(int(digits) if digits else 0)
    return tuple(out) if out else (0,)


def newer_release(current: str | None = None) -> str | None:
    """Return tag like 'v1.0.2' if GitHub latest is newer, else None."""
    now = _parse(current or __version__)
    req = urllib.request.Request(
        API_LATEST,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"ScanDeck/{__version__}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return None
    tag = data.get("tag_name") if isinstance(data, dict) else None
    if not isinstance(tag, str) or not tag.strip():
        return None
    tag = tag.strip()
    if _parse(tag) > now:
        return tag
    return None
