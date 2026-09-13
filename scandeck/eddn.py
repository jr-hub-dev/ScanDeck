"""Envoi live vers EDDN + journal des acceptations / rejets."""

from __future__ import annotations

import json
import queue
import sys
import threading
import urllib.error
import urllib.request
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from . import __version__
from .config import load as load_config, user_data_dir

UPLOAD_URL = "https://eddn.edcd.io:4430/upload/"
SCHEMA = "https://eddn.edcd.io/schemas/{name}/1"
SOFTWARE = f"ScanDeck [{sys.platform}]"
MAX_LOG = 250
JOURNAL_EVENTS = {"Location", "FSDJump", "Docked", "Scan", "SAASignalsFound", "CarrierJump"}
OWN_SCHEMA = {
    "FSSDiscoveryScan": "fssdiscoveryscan",
    "FSSBodySignals": "fssbodysignals",
    "FSSAllBodiesFound": "fssallbodiesfound",
    "ScanBaryCentre": "scanbarycentre",
    "CodexEntry": "codexentry",
}
JOURNAL_DROP = {
    "ActiveFine",
    "CockpitBreach",
    "BoostUsed",
    "FuelLevel",
    "FuelUsed",
    "JumpDist",
    "Latitude",
    "Longitude",
    "Wanted",
}
FACTION_DROP = {"HappiestSystem", "HomeSystem", "MyReputation", "SquadronFaction"}
CODEX_DROP = {"IsNewEntry", "NewTraitsDiscovered", "VoucherAmount"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def filter_localised(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            k: filter_localised(v)
            for k, v in data.items()
            if not str(k).endswith("_Localised")
        }
    if isinstance(data, list):
        return [filter_localised(x) for x in data]
    return data


class EddnHub:
    def __init__(self) -> None:
        self.enabled = True
        self.cmdr = ""
        self.fid = ""
        self.gameversion = ""
        self.gamebuild = ""
        self.horizons = True
        self.odyssey = True
        self.system = ""
        self.system_address: int | None = None
        self.starpos: list | None = None
        self.body = ""
        self.explore_rank: int | None = None
        self.explore_progress: int | None = None
        self.exo_rank: int | None = None
        self.exo_progress: int | None = None
        self._fss: list[dict] = []
        self._fss_timer: threading.Timer | None = None
        self._log: deque[dict] = deque(maxlen=MAX_LOG)
        self._lock = threading.Lock()
        self._fss_lock = threading.Lock()
        self._q: queue.Queue = queue.Queue()
        self._counts = {"ok": 0, "rejected": 0, "error": 0}
        self.reload_config()
        threading.Thread(target=self._worker, daemon=True, name="eddn-send").start()

    def reload_config(self) -> None:
        self.enabled = bool(load_config().get("eddn_enabled", True))

    def logs(self) -> list[dict]:
        with self._lock:
            return list(self._log)

    def counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def observe(self, event: dict) -> None:
        name = event.get("event")
        if name == "Fileheader":
            self.gameversion = str(event.get("gameversion") or self.gameversion)
            self.gamebuild = str(event.get("build") or self.gamebuild)
        elif name == "LoadGame":
            self.cmdr = str(event.get("Commander") or self.cmdr)
            self.fid = str(event.get("FID") or self.fid)
            self.gameversion = str(event.get("gameversion") or self.gameversion)
            self.gamebuild = str(event.get("build") or self.gamebuild)
            if "horizons" in event:
                self.horizons = bool(event.get("horizons"))
            if "odyssey" in event:
                self.odyssey = bool(event.get("odyssey"))
        elif name in {"FSDJump", "Location", "CarrierJump"}:
            self.system = event.get("StarSystem") or self.system
            addr = event.get("SystemAddress")
            if addr is not None:
                self.system_address = int(addr)
            if event.get("StarPos"):
                self.starpos = list(event["StarPos"])
            self.body = event.get("Body") or self.body
        elif name == "ApproachBody":
            self.body = event.get("Body") or self.body
        elif name == "Rank":
            if event.get("Explore") is not None:
                self.explore_rank = int(event["Explore"])
            if event.get("Exobiologist") is not None:
                self.exo_rank = int(event["Exobiologist"])
        elif name == "Progress":
            if event.get("Explore") is not None:
                self.explore_progress = int(event["Explore"])
            if event.get("Exobiologist") is not None:
                self.exo_progress = int(event["Exobiologist"])

    def offer(self, event: dict) -> None:
        if not self.enabled:
            return
        name = event.get("event")
        if name == "FSSSignalDiscovered":
            with self._fss_lock:
                self._fss.append(deepcopy(event))
                if self._fss_timer is not None:
                    self._fss_timer.cancel()
                self._fss_timer = threading.Timer(2.0, self.flush_fss)
                self._fss_timer.daemon = True
                self._fss_timer.start()
            return
        self.flush_fss()
        msg = self._build(event)
        if msg:
            self._q.put(msg)

    def flush_fss(self) -> None:
        with self._fss_lock:
            pending = list(self._fss)
            self._fss = []
            if self._fss_timer is not None:
                self._fss_timer.cancel()
                self._fss_timer = None
        if not pending or not self.enabled:
            return
        signals = []
        addr = self.system_address
        for raw in pending:
            if addr is not None and raw.get("SystemAddress") not in (None, addr):
                continue
            if raw.get("USSType") == "$USS_Type_MissionTarget;":
                continue
            sig = filter_localised(deepcopy(raw))
            for k in ("event", "horizons", "odyssey", "TimeRemaining", "SystemAddress"):
                sig.pop(k, None)
            signals.append(sig)
        if not signals or not self.cmdr or not self.starpos:
            return
        body = {
            "event": "FSSSignalDiscovered",
            "timestamp": signals[0].get("timestamp") or _now(),
            "SystemAddress": addr,
            "StarSystem": self.system,
            "StarPos": list(self.starpos),
            "signals": signals,
            "horizons": self.horizons,
            "odyssey": self.odyssey,
        }
        self._q.put(self._wrap("fsssignaldiscovered", body, "FSSSignalDiscovered"))

    def _build(self, event: dict) -> dict | None:
        name = event.get("event")
        if not name or not self.cmdr:
            return None
        if name in OWN_SCHEMA:
            return self._own(event, OWN_SCHEMA[name])
        if name in JOURNAL_EVENTS:
            return self._journal(event)
        return None

    def _own(self, event: dict, schema: str) -> dict | None:
        entry = filter_localised(deepcopy(event))
        if event.get("event") == "FSSDiscoveryScan":
            entry.pop("Progress", None)
        if event.get("event") == "CodexEntry":
            for k in CODEX_DROP:
                entry.pop(k, None)
            if not all(entry.get(k) for k in ("System", "Name", "Region", "Category", "SubCategory")):
                return None
        addr = entry.get("SystemAddress", self.system_address)
        if self.system_address is not None and addr not in (None, self.system_address):
            return None
        if "StarSystem" not in entry and "System" not in entry and self.system:
            entry["StarSystem"] = self.system
        if "StarPos" not in entry:
            if not self.starpos:
                return None
            entry["StarPos"] = list(self.starpos)
        if "SystemAddress" not in entry and self.system_address is not None:
            entry["SystemAddress"] = self.system_address
        entry["horizons"] = self.horizons
        entry["odyssey"] = self.odyssey
        return self._wrap(schema, entry, event.get("event") or schema)

    def _journal(self, event: dict) -> dict | None:
        entry = filter_localised(deepcopy(event))
        for k in JOURNAL_DROP:
            entry.pop(k, None)
        if "Factions" in entry:
            entry["Factions"] = [
                {k: v for k, v in fac.items() if k not in FACTION_DROP}
                for fac in entry["Factions"]
            ]
        addr = entry.get("SystemAddress", self.system_address)
        if addr is None:
            return None
        if "StarSystem" not in entry:
            if self.system_address != addr or not self.system:
                return None
            entry["StarSystem"] = self.system
        if "StarPos" not in entry:
            if self.system_address != addr or not self.starpos:
                return None
            entry["StarPos"] = list(self.starpos)
        entry["horizons"] = self.horizons
        entry["odyssey"] = self.odyssey
        return self._wrap("journal", entry, event.get("event") or "journal")

    def _wrap(self, schema: str, message: dict, label: str) -> dict:
        ref = SCHEMA.format(name=schema)
        gv = (self.gameversion or "").lower()
        if "beta" in gv or "alpha" in gv:
            ref = f"{ref}/test"
        return {
            "_label": label,
            "_schema": schema,
            "payload": {
                "$schemaRef": ref,
                "header": {
                    "uploaderID": self.cmdr,
                    "softwareName": SOFTWARE,
                    "softwareVersion": __version__,
                    "gameversion": self.gameversion or "",
                    "gamebuild": self.gamebuild or "",
                },
                "message": message,
            },
        }

    def _worker(self) -> None:
        while True:
            item = self._q.get()
            try:
                self._post(item)
            except Exception as exc:
                self._record("error", item, detail=str(exc))

    def _post(self, item: dict) -> None:
        raw = json.dumps(item["payload"], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        req = urllib.request.Request(
            UPLOAD_URL,
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
            self._record(
                "rejected" if exc.code in {400, 426} else "error",
                item,
                code=exc.code,
                detail=body[:400],
            )
            return
        except urllib.error.URLError as exc:
            self._record("error", item, detail=str(exc.reason or exc))
            return
        ok = code == 200 and body.strip().upper().startswith("OK")
        self._record("ok" if ok else "rejected", item, code=code, detail=body[:400])

    def _record(self, status: str, item: dict, *, code: int | None = None, detail: str = "") -> None:
        row = {
            "ts": _now(),
            "status": status,
            "event": item.get("_label") or "",
            "schema": item.get("_schema") or "",
            "code": code,
            "detail": detail,
        }
        with self._lock:
            self._log.append(row)
            if status in self._counts:
                self._counts[status] += 1
        try:
            path = user_data_dir() / "eddn.log"
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            if path.stat().st_size > 400_000:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass


_hub: EddnHub | None = None
_hub_lock = threading.Lock()


def get_hub() -> EddnHub:
    global _hub
    with _hub_lock:
        if _hub is None:
            _hub = EddnHub()
        return _hub
