from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterator
from pathlib import Path

JOURNAL_CANDIDATES = [
    Path.home() / "Saved Games/Frontier Developments/Elite Dangerous",
    Path.home() / "Games/EliteDangerous/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous",
    Path.home() / ".local/share/Steam/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous",
    Path.home() / ".steam/steam/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous",
    Path.home() / "Games/Heroic/Prefixes/Elite Dangerous/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous",
]

GRAVITY_MS2_TO_G = 9.81
PRESSURE_PA_TO_ATM = 101325.0

BIO_EVENTS = {
    "Fileheader",
    "Location",
    "FSDJump",
    "CarrierJump",
    "Scan",
    "FSSDiscoveryScan",
    "FSSSignalDiscovered",
    "FSSAllBodiesFound",
    "FSSBodySignals",
    "SAAScanComplete",
    "SAASignalsFound",
    "ScanOrganic",
    "CodexEntry",
    "ApproachBody",
    "Touchdown",
    "Liftoff",
    "Rank",
    "Progress",
    "Promotion",
    "Statistics",
    "SellOrganicData",
    "SellExplorationData",
    "MultiSellExplorationData",
}


def find_journal_dir(explicit: str | None = None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_dir():
            from .i18n import t
            raise FileNotFoundError(t("journal_missing_path", path=path))
        return path
    env = os.environ.get("ED_JOURNAL_DIR")
    if env:
        return Path(env).expanduser()
    for candidate in JOURNAL_CANDIDATES:
        if candidate.is_dir() and any(candidate.glob("Journal.*.log")):
            return candidate
    from .i18n import t
    raise FileNotFoundError(t("journal_missing"))


def guessed_journal_dir() -> Path | None:
    """Folder auto-detect would pick, or None."""
    env = os.environ.get("ED_JOURNAL_DIR")
    if env:
        path = Path(env).expanduser()
        if path.is_dir():
            return path
    for candidate in JOURNAL_CANDIDATES:
        if candidate.is_dir() and any(candidate.glob("Journal.*.log")):
            return candidate
    return None


def resolve_journal_dir(explicit: str | None = None) -> Path:
    """CLI path, then saved Options, then auto-detect."""
    if explicit and str(explicit).strip():
        return find_journal_dir(explicit.strip())
    from .config import load
    saved = (load().get("journal_dir") or "").strip()
    if saved:
        return find_journal_dir(saved)
    return find_journal_dir(None)


def latest_journal(journal_dir: Path) -> Path | None:
    files = sorted(journal_dir.glob("Journal.*.log"), key=lambda p: p.name)
    return files[-1] if files else None


def recent_journals(journal_dir: Path, *, days: int = 7, limit: int = 40) -> list[Path]:
    """Journaux récents, du plus ancien au plus récent (reprise après extinction)."""
    files = sorted(journal_dir.glob("Journal.*.log"), key=lambda p: p.name)
    if not files:
        return []
    cutoff = time.time() - days * 86400
    picked = [p for p in files if p.stat().st_mtime >= cutoff]
    if not picked:
        return files[-1:]
    return picked[-limit:]


def parse_line(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def gravity_g(surface_gravity: float | None) -> float | None:
    if surface_gravity is None:
        return None
    return surface_gravity / GRAVITY_MS2_TO_G


def pressure_atm(surface_pressure: float | None) -> float | None:
    if surface_pressure is None:
        return None
    return surface_pressure / PRESSURE_PA_TO_ATM


def composition_map(items: list[dict] | None) -> dict[str, float]:
    if not items:
        return {}
    return {i["Name"]: float(i.get("Percent", 0)) for i in items if "Name" in i}


def bio_count_from_signals(signals: list[dict] | None) -> int | None:
    if not signals:
        return None
    for sig in signals:
        typ = sig.get("Type", "")
        if "Biological" in typ or sig.get("Type_Localised") in {
            "Biological", "Biologique", "Biológico",
        }:
            return int(sig.get("Count", 0))
    return 0


def geo_count_from_signals(signals: list[dict] | None) -> int | None:
    if not signals:
        return None
    for sig in signals:
        typ = sig.get("Type", "")
        if "Geological" in typ or sig.get("Type_Localised") in {
            "Geological", "Géologique", "Geológico",
        }:
            return int(sig.get("Count", 0))
    return None


def is_notable_stellar_phenomenon(event: dict) -> bool:
    """Honk FSSSignalDiscovered for Notable Stellar Phenomena (clouds / rings)."""
    name = event.get("SignalName") or ""
    if name.startswith("$Fixed_Event_Life_"):
        return True
    loc = (event.get("SignalName_Localised") or "").casefold()
    needles = (
        "notable stellar",
        "phénomène stellaire",
        "phenomene stellaire",
        "fenómeno estelar",
        "fenomeno estelar",
    )
    return any(n in loc for n in needles)


def is_nsp_codex(event: dict) -> bool:
    """Codex scan of a notable stellar phenomenon (not a planetary bio)."""
    dest = event.get("NearestDestination") or ""
    if dest.startswith("$Fixed_Event_Life_"):
        return True
    name = event.get("Name") or ""
    return name.startswith("$Codex_Ent_L_")


def genuses_from_event(event: dict) -> list[str]:
    names = []
    for item in event.get("Genuses") or []:
        name = item.get("Genus_Localised") or item.get("Genus") or ""
        names.append(name)
    return [n for n in names if n]


class JournalWatcher:
    def __init__(self, journal_dir: Path, poll_s: float = 0.25) -> None:
        self.journal_dir = journal_dir
        self.poll_s = poll_s
        self.path: Path | None = None
        self._fh = None
        self._inode: int | None = None

    def _open(self, path: Path, from_start: bool) -> None:
        if self._fh:
            self._fh.close()
        self.path = path
        self._fh = path.open("r", encoding="utf-8", errors="replace")
        self._inode = path.stat().st_ino
        if not from_start:
            self._fh.seek(0, os.SEEK_END)

    def follow(self, from_start: bool = True, start_offset: int | None = None) -> Iterator[dict]:
        current = latest_journal(self.journal_dir)
        if current is None:
            raise FileNotFoundError(f"Aucun Journal.*.log dans {self.journal_dir}")
        self._open(current, from_start=from_start)
        assert self._fh is not None
        if start_offset is not None:
            self._fh.seek(start_offset)
        while True:
            line = self._fh.readline()
            if line:
                event = parse_line(line)
                if event and event.get("event") in BIO_EVENTS:
                    yield event
                continue
            latest = latest_journal(self.journal_dir)
            if latest and (latest != self.path or latest.stat().st_ino != self._inode):
                leftover = self._fh.read()
                for raw in leftover.splitlines():
                    event = parse_line(raw)
                    if event and event.get("event") in BIO_EVENTS:
                        yield event
                self._open(latest, from_start=True)
                continue
            time.sleep(self.poll_s)
            line = self._fh.readline()
            if line:
                event = parse_line(line)
                if event and event.get("event") in BIO_EVENTS:
                    yield event
                continue
            latest = latest_journal(self.journal_dir)
            if latest and (latest != self.path or latest.stat().st_ino != self._inode):
                leftover = self._fh.read()
                for raw in leftover.splitlines():
                    event = parse_line(raw)
                    if event and event.get("event") in BIO_EVENTS:
                        yield event
                self._open(latest, from_start=True)
                continue
            time.sleep(self.poll_s)

    def iter_file(self, path: Path) -> Iterator[dict]:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                event = parse_line(line)
                if event and event.get("event") in BIO_EVENTS:
                    yield event


def replay_files(paths: list[Path]) -> Iterator[dict]:
    for path in paths:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                event = parse_line(line)
                if event and event.get("event") in BIO_EVENTS:
                    yield event
