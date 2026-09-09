from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .i18n import apply_fileheader, t
from .catalog import Catalog, DATA_DIR
from .criteria import CriteriaEngine
from .display import (
    print_block,
    render_body,
    snapshot_body,
    snapshot_system,
    snapshot_system_row,
    stub_snapshot,
    fmt_m_compact,
)
from .spreadsheet import ExobioWorkbook, HAS_OPENPYXL
from .journal import (
    JournalWatcher,
    bio_count_from_signals,
    composition_map,
    geo_count_from_signals,
    resolve_journal_dir,
    genuses_from_event,
    gravity_g,
    latest_journal,
    pressure_atm,
    recent_journals,
    replay_files,
)
from .matcher import Matcher, verdict
from .models import BodyState, OrganicProgress, ScanProgress
from .ranks import EXPLORE_RANKS, from_credits, from_journal
from .scan_value import carto_stock_value


class Session:
    def __init__(
        self,
        catalog: Catalog,
        matcher: Matcher,
        *,
        live_display: bool = True,
        workbook: "ExobioWorkbook | None" = None,
    ) -> None:
        self.catalog = catalog
        self.matcher = matcher
        self.live_display = live_display
        self.wb = workbook
        self.system_name = ""
        self.system_address: int | None = None
        self.star_types: dict[int, list[str]] = defaultdict(list)
        self.stars: dict[tuple[int | None, int | None], str] = {}
        self.bodies: dict[tuple[int | None, int | None], BodyState] = {}
        self.progress: dict[tuple[int | None, int], dict[str, OrganicProgress]] = defaultdict(dict)
        self.catching_up = False
        self._on_ground = False   # True après Touchdown, False après Liftoff
        self.on_update = None
        self._focus_id: int | None = None
        self._sys_sig: str | None = None
        self.fss_body_count: int | None = None
        self.fss_complete = False
        self.exo_rank: int | None = None
        self.exo_progress: int | None = None
        self.organic_profits: int | None = None
        self.explore_rank: int | None = None
        self.explore_progress: int | None = None
        self.explore_profits: int | None = None
        # UC vendus depuis le dernier Progress Explore (le total à vie ne colle pas aux paliers).
        self.explore_sold_since_progress: int = 0
        self.hold: dict[tuple, int] = {}
        self.carto_hold: dict[tuple, int] = {}

    def body(self, system_address: int | None, body_id: int | None, name: str = "") -> BodyState:
        key = (system_address, body_id)
        state = self.bodies.get(key)
        if state is None:
            state = BodyState(
                system_name=self.system_name,
                system_address=system_address,
                body_id=body_id,
                body_name=name,
            )
            self.bodies[key] = state
        if name:
            state.body_name = name
        if system_address is not None:
            state.star_types = list(self.star_types.get(system_address, []))
        return state

    def handle(self, event: dict) -> None:
        name = event.get("event")
        handler = getattr(self, f"on_{name}", None)
        if handler:
            handler(event)

    def on_Fileheader(self, event: dict) -> None:
        apply_fileheader(event.get("language"))
        if self.on_update and not self.catching_up:
            self._emit_rank()
            self._emit_explore_rank()
            self._emit_hold()

    def on_Location(self, event: dict) -> None:
        self.system_name = event.get("StarSystem") or self.system_name
        self.system_address = event.get("SystemAddress", self.system_address)
        if event.get("Latitude") is not None or event.get("InSRV") or event.get("OnFoot"):
            self._on_ground = True
        else:
            self._on_ground = False
        if event.get("BodyType") == "Planet" or event.get("Latitude") is not None:
            body = self.body(event.get("SystemAddress"), event.get("BodyID"), event.get("Body") or "")
            self._touch(body, event)

    def on_FSDJump(self, event: dict) -> None:
        self.on_Location(event)
        self._focus_id = None
        self.fss_body_count = None
        self.fss_complete = False
        self._emit_system()

    def on_CarrierJump(self, event: dict) -> None:
        self.on_FSDJump(event)

    def on_ApproachBody(self, event: dict) -> None:
        self.system_name = event.get("StarSystem") or self.system_name
        self.system_address = event.get("SystemAddress", self.system_address)
        body = self.body(event.get("SystemAddress"), event.get("BodyID"), event.get("Body") or "")
        self._touch(body, event)
        if body.planet_class or body.star_type or body.bio_count:
            self.maybe_display(body, force=True, select=True)
        else:
            self._emit_system()

    def _touch(self, body: BodyState, event: dict) -> None:
        ts = event.get("timestamp") or ""
        if ts:
            body.last_ts = ts

    def on_Rank(self, event: dict) -> None:
        if "Exobiologist" in event:
            self.exo_rank = int(event["Exobiologist"])
            self._emit_rank()
        if "Explore" in event:
            new_rank = int(event["Explore"])
            if new_rank != self.explore_rank:
                self.explore_sold_since_progress = 0
            self.explore_rank = new_rank
            self._emit_explore_rank()

    def on_Progress(self, event: dict) -> None:
        if "Exobiologist" in event:
            self.exo_progress = int(event["Exobiologist"])
            self._emit_rank()
        if "Explore" in event:
            new_progress = int(event["Explore"])
            if new_progress != self.explore_progress:
                self.explore_sold_since_progress = 0
            self.explore_progress = new_progress
            self._emit_explore_rank()

    def on_Promotion(self, event: dict) -> None:
        if "Exobiologist" in event:
            self.exo_rank = int(event["Exobiologist"])
            self.exo_progress = 0
            self._emit_rank()
        if "Explore" in event:
            self.explore_rank = int(event["Explore"])
            self.explore_progress = 0
            self.explore_sold_since_progress = 0
            self._emit_explore_rank()

    def on_Statistics(self, event: dict) -> None:
        exo = event.get("Exobiology") or {}
        profits = exo.get("Organic_Data_Profits")
        if profits is not None:
            self.organic_profits = int(profits)
            self._emit_rank()
        exploration = event.get("Exploration") or {}
        expl_profits = exploration.get("Exploration_Profits")
        if expl_profits is not None:
            self.explore_profits = int(expl_profits)
            self._emit_explore_rank()

    def on_SellOrganicData(self, event: dict) -> None:
        gained = 0
        for item in event.get("BioData") or []:
            gained += int(item.get("Value") or 0) + int(item.get("Bonus") or 0)
        if gained:
            self.organic_profits = (self.organic_profits or 0) + gained
            self._emit_rank()
        self._hold_clear()

    def on_SellExplorationData(self, event: dict) -> None:
        gained = int(event.get("TotalEarnings") or 0)
        if not gained:
            gained = int(event.get("BaseValue") or 0) + int(event.get("Bonus") or 0)
        if gained:
            self.explore_profits = (self.explore_profits or 0) + gained
            self.explore_sold_since_progress += gained
            self._emit_explore_rank()
        self._carto_clear()

    def on_MultiSellExplorationData(self, event: dict) -> None:
        self.on_SellExplorationData(event)

    def rank_snapshot(self) -> dict:
        if self.organic_profits is not None:
            snap = from_credits(self.organic_profits)
        else:
            snap = from_journal(self.exo_rank, self.exo_progress, None)
        snap["_rank"] = True
        snap["game_rank"] = self.exo_rank
        snap["game_progress"] = self.exo_progress
        return snap

    def explore_rank_snapshot(self) -> dict:
        # Aiguille = rang + % journal. Le total UC à vie ne colle pas aux paliers wiki,
        # donc « encore » = restant interpolé, moins les ventes depuis le dernier Progress.
        snap = from_journal(
            self.explore_rank, self.explore_progress, None, EXPLORE_RANKS,
        )
        sold = self.explore_sold_since_progress
        remain = snap.get("remain")
        if sold and remain is not None:
            snap["remain"] = max(0, remain - sold)
            idx = snap.get("rank_id")
            if idx is not None and idx < len(EXPLORE_RANKS) - 1:
                span = EXPLORE_RANKS[idx + 1]["cr"] - EXPLORE_RANKS[idx]["cr"]
                if span > 0:
                    snap["frac"] = max(0.0, min(0.999, 1.0 - snap["remain"] / span))
        snap["_explore_rank"] = True
        snap["game_rank"] = self.explore_rank
        snap["game_progress"] = self.explore_progress
        return snap

    def _emit_rank(self) -> None:
        if self.catching_up or not self.on_update:
            return
        self.on_update(self.rank_snapshot())

    def _emit_explore_rank(self) -> None:
        if self.catching_up or not self.on_update:
            return
        self.on_update(self.explore_rank_snapshot())

    def hold_snapshot(self) -> dict:
        bio_cr = sum(self.hold.values())
        carto_cr = sum(self.carto_hold.values())
        return {
            "_hold": True,
            "cr": bio_cr,
            "n": len(self.hold),
            "bio_cr": bio_cr,
            "bio_n": len(self.hold),
            "carto_cr": carto_cr,
            "carto_n": len(self.carto_hold),
        }

    def _emit_hold(self) -> None:
        if self.catching_up or not self.on_update:
            return
        self.on_update(self.hold_snapshot())

    def seed_hold_from_workbook(self) -> None:
        if not self.wb:
            return
        self.hold = self.wb.unsold_hold(self.catalog)

    def _hold_add(self, address, body_id, species_name: str) -> None:
        sp = self.catalog.get(species_name)
        self.hold[(address, body_id, species_name)] = sp.value_cr if sp else 0
        self._emit_hold()

    def _hold_clear(self) -> None:
        self.hold.clear()
        if self.wb:
            self.wb.mark_all_sold()
        self._emit_hold()

    def _carto_refresh(self, body: BodyState) -> None:
        if _is_clutter(body):
            return
        val = carto_stock_value(body)
        key = (body.system_address, body.body_id)
        if val:
            self.carto_hold[key] = val
        else:
            self.carto_hold.pop(key, None)
        self._emit_hold()

    def _carto_clear(self) -> None:
        self.carto_hold.clear()
        self._emit_hold()

    def on_Touchdown(self, event: dict) -> None:
        self._on_ground = True

    def on_Liftoff(self, event: dict) -> None:
        self._on_ground = False

    def on_Scan(self, event: dict) -> None:
        system = event.get("StarSystem") or self.system_name
        address = event.get("SystemAddress", self.system_address)
        if event.get("StarType"):
            spectral = _spectral_type(event)
            body_id = event.get("BodyID")
            if address is not None and spectral:
                types = self.star_types[address]
                if event["StarType"] not in types:
                    types.append(event["StarType"])
                self.stars[(address, body_id)] = spectral
                for other in self.bodies.values():
                    if other.system_address == address and other.parent_star_id == body_id:
                        other.parent_star = spectral
            self.system_name = system or self.system_name
            if address is not None:
                self.system_address = address
            body = self.body(address, body_id, event.get("BodyName", ""))
            body.system_name = system or body.system_name
            body.star_type = spectral
            body.star_class = event.get("StarType")
            body.stellar_mass = event.get("StellarMass")
            body.temperature_k = event.get("SurfaceTemperature")
            body.distance_ls = event.get("DistanceFromArrivalLS")
            if "WasDiscovered" in event:
                body.was_discovered = bool(event.get("WasDiscovered"))
            self._touch(body, event)
            if (event.get("ScanType") or "").lower() != "navbeacondetail":
                self._carto_refresh(body)
            self._emit_system()
            return
        if not event.get("PlanetClass"):
            return
        self.system_name = system or self.system_name
        self.system_address = address
        body = self.body(address, event.get("BodyID"), event.get("BodyName", ""))
        body.system_name = system or body.system_name
        body.planet_class = event.get("PlanetClass")
        body.atmosphere = event.get("Atmosphere") or ""
        body.atmosphere_type = event.get("AtmosphereType")
        body.atmosphere_composition = composition_map(event.get("AtmosphereComposition"))
        body.volcanism = event.get("Volcanism") or ""
        body.temperature_k = event.get("SurfaceTemperature")
        body.gravity_g = gravity_g(event.get("SurfaceGravity"))
        body.pressure_atm = pressure_atm(event.get("SurfacePressure"))
        body.materials = composition_map(event.get("Materials"))
        body.distance_ls = event.get("DistanceFromArrivalLS")
        body.landable = event.get("Landable")
        body.mass_em = event.get("MassEM")
        tf = (event.get("TerraformState") or "").lower()
        body.terraformable = tf.startswith("terraform")
        if "WasDiscovered" in event:
            body.was_discovered = bool(event.get("WasDiscovered"))
        if "WasMapped" in event:
            body.was_mapped = bool(event.get("WasMapped"))
        if "WasFootfalled" in event:
            body.was_footfalled = bool(event.get("WasFootfalled"))
        body.star_types = list(self.star_types.get(address or -1, []))
        body.parent_star_id = _parent_star_id(event)
        if body.parent_star_id is not None:
            body.parent_star = self.stars.get((address, body.parent_star_id))
        self._touch(body, event)
        if (event.get("ScanType") or "").lower() != "navbeacondetail":
            self._carto_refresh(body)
        if body.bio_count and body.dss_complete:
            self.maybe_display(body, select=False)
        else:
            self._emit_system()

    def on_FSSBodySignals(self, event: dict) -> None:
        addr = event.get("SystemAddress", self.system_address)
        if addr is not None:
            self.system_address = addr
        body = self.body(addr, event.get("BodyID"), event.get("BodyName", ""))
        if self.system_name:
            body.system_name = body.system_name or self.system_name
        count = bio_count_from_signals(event.get("Signals"))
        if count is not None:
            body.bio_count = count
        geo = geo_count_from_signals(event.get("Signals"))
        if geo is not None:
            body.geo_count = geo
        self._emit_system()

    def on_FSSDiscoveryScan(self, event: dict) -> None:
        addr = event.get("SystemAddress")
        if addr is not None:
            self.system_address = addr
        count = event.get("BodyCount")
        if count is not None:
            self.fss_body_count = int(count)
        self.fss_complete = False
        self._emit_system()

    def on_FSSAllBodiesFound(self, event: dict) -> None:
        addr = event.get("SystemAddress")
        if addr is not None:
            self.system_address = addr
        self.system_name = event.get("StarSystem") or self.system_name
        count = event.get("Count")
        if count is not None:
            self.fss_body_count = int(count)
        self.fss_complete = True
        self._emit_system()

    def on_SAAScanComplete(self, event: dict) -> None:
        body = self.body(event.get("SystemAddress"), event.get("BodyID"), event.get("BodyName", ""))
        body.dss_complete = True
        body.mapped = True
        self._carto_refresh(body)
        if body.bio_count:
            self.maybe_display(body, select=True)
        else:
            self._emit_system()

    def on_SAASignalsFound(self, event: dict) -> None:
        body = self.body(event.get("SystemAddress"), event.get("BodyID"), event.get("BodyName", ""))
        count = bio_count_from_signals(event.get("Signals"))
        if count is not None:
            body.bio_count = count
        geo = geo_count_from_signals(event.get("Signals"))
        if geo is not None:
            body.geo_count = geo
        genuses = genuses_from_event(event)
        if genuses:
            body.dss_genuses = genuses
        body.dss_complete = True
        body.mapped = True
        self._touch(body, event)
        self._carto_refresh(body)
        if body.bio_count:
            self.maybe_display(body, select=True)
        if self.wb and body.dss_genuses:
            self.wb.on_dss(body, timestamp=event.get("timestamp"), catalog=self.catalog)

    def _english_species(self, event: dict) -> tuple[str, str]:
        codex = event.get("Species") or event.get("Name") or ""
        found = self.catalog.by_codex(codex) if codex else None
        if found is None and codex:
            # CodexEntry uses variant keys like $Codex_Ent_Stratum_07_K_Name;
            for key, species in self.catalog._by_codex.items():
                prefix = key.replace("_Name;", "_")
                if codex.startswith(prefix):
                    found = species
                    break
        if found:
            return found.genus, found.name
        local = event.get("Species_Localised") or event.get("Name_Localised") or ""
        if " - " in local:
            local = local.split(" - ")[0].strip()
        local = local.replace("Touradon", "Tussock")
        genus = event.get("Genus_Localised") or local.split(" ", 1)[0]
        genus = self.catalog.resolve_genus(genus) or genus
        return genus, local

    def on_ScanOrganic(self, event: dict) -> None:
        address = event.get("SystemAddress")
        body_id = event.get("Body")
        genus, species_name = self._english_species(event)
        scan_type = (event.get("ScanType") or "").lower()
        key = (address, body_id)
        bucket = self.progress[key]
        org = bucket.get(species_name)
        if org is None:
            org = OrganicProgress(genus=genus, species_name=species_name)
            bucket[species_name] = org
        org.variant = event.get("Variant_Localised") or org.variant
        if scan_type == "log":
            if self._on_ground:
                org.stage = ScanProgress.LOG
                org.sample_count = max(org.sample_count, 1)
            # sinon : Nomad en vol → espèce/variante connues, pas un échantillon
        elif scan_type == "sample":
            org.sample_count = min(max(org.sample_count + 1, 2), 2)
            org.stage = ScanProgress.SAMPLE
        elif scan_type == "analyse":
            org.stage = ScanProgress.ANALYSE
            org.sample_count = 3
            self._hold_add(address, body_id, species_name)
        body = self.body(address, body_id)
        self._touch(body, event)
        self.maybe_display(body, select=False)
        if self.wb:
            self.wb.on_scan_organic(
                body,
                genus=genus,
                species_name=species_name,
                variant=org.variant,
                stage=org.stage,
                catalog=self.catalog,
            )
            # vérifier si la planète est terminée
            if org.stage == ScanProgress.ANALYSE:
                bucket = self.progress[key]
                done_count = sum(1 for o in bucket.values() if o.stage == ScanProgress.ANALYSE)
                if body.bio_count and done_count >= body.bio_count:
                    self.wb.mark_planet_done(body)

    def on_CodexEntry(self, event: dict) -> None:
        sub = (event.get("SubCategory_Localised") or event.get("SubCategory") or "").lower()
        if "organ" not in sub:
            return
        address = event.get("SystemAddress")
        body_id = event.get("BodyID")
        if address is None or body_id is None:
            return
        body = self.bodies.get((address, body_id))
        if body is None:
            return
        genus, species_name = self._english_species(event)
        if not species_name:
            return
        bucket = self.progress[(address, body_id)]
        org = bucket.get(species_name)
        if org is None:
            org = OrganicProgress(genus=genus, species_name=species_name)
            bucket[species_name] = org
        local = event.get("Name_Localised") or event.get("Name") or ""
        if local:
            org.variant = org.variant or local
        if self._on_ground and org.stage == ScanProgress.NONE:
            org.stage = ScanProgress.LOG
            org.sample_count = max(org.sample_count, 1)
        self._touch(body, event)
        self.maybe_display(body, select=False)
        if self.wb:
            self.wb.on_scan_organic(
                body,
                genus=genus,
                species_name=species_name,
                variant=org.variant,
                stage=org.stage,
                catalog=self.catalog,
            )

    def _visible_bodies(self) -> list[BodyState]:
        addr = self.system_address
        return [
            b for b in self.bodies.values()
            if b.system_address == addr and not _is_clutter(b)
        ]

    def _matches(self, body: BodyState):
        return self.matcher.match(
            body, self.progress.get((body.system_address, body.body_id)),
        )

    def _system_payload(self, selected_id: int | None) -> dict:
        rows = []
        for body in self._visible_bodies():
            matches = (
                self._matches(body)
                if body.planet_class or body.dss_genuses
                else []
            )
            rows.append(
                snapshot_system_row(
                    body,
                    matches,
                    catalog=self.catalog,
                    progress=self.progress.get((body.system_address, body.body_id)),
                )
            )
        payload = snapshot_system(
            rows,
            self.system_name,
            fss_body_count=self.fss_body_count,
            fss_complete=self.fss_complete,
        )
        payload["selected_id"] = selected_id
        return payload

    def _system_sig(self, payload: dict) -> str:
        parts = [
            payload.get("system") or "",
            str(payload.get("selected_id")),
            str(payload.get("fss_body_count")),
            str(payload.get("fss_complete")),
            payload.get("sys_value") or "",
        ]
        for row in payload.get("system_bodies") or []:
            parts.append(
                f"{row.get('body_id')}|{row.get('kind')}|{row.get('bios')}|"
                f"{row.get('lo')}|{row.get('hi')}|{row.get('status')}|{row.get('tier')}"
            )
        return "|".join(parts)

    def _emit_system(self) -> None:
        if self.catching_up or not self.on_update:
            return
        payload = self._system_payload(self._focus_id)
        sig = self._system_sig(payload)
        if sig == self._sys_sig:
            return
        self._sys_sig = sig
        payload["_system"] = True
        payload["select"] = False
        self.on_update(payload)

    def maybe_display(self, body: BodyState, force: bool = False, select: bool = False) -> None:
        if self.catching_up:
            return
        if select:
            self._focus_id = body.body_id
        can_match = bool(body.planet_class or body.dss_genuses)
        if not can_match:
            payload = self._system_payload(self._focus_id)
            snap = stub_snapshot(body, [])
            snap.update(payload)
            snap["body_id"] = body.body_id
            snap["select"] = select
            self._sys_sig = self._system_sig(payload)
            if self.on_update:
                self.on_update(snap)
            return
        matches = self._matches(body)
        _, alert, _ = verdict(matches, body)
        signature = self._signature(body, matches)
        payload = self._system_payload(self._focus_id)
        sys_sig = self._system_sig(payload)
        if not force and signature == body.displayed_signature and sys_sig == self._sys_sig:
            return
        body.displayed_signature = signature
        self._sys_sig = sys_sig
        prog = self.progress.get((body.system_address, body.body_id)) or {}
        if body.dss_complete or prog:
            snap = snapshot_body(body, matches, alert=alert, catalog=self.catalog)
            if self.live_display:
                print_block(render_body(body, matches, alert=alert))
        else:
            snap = stub_snapshot(body, matches)
        snap.update(payload)
        snap["body_id"] = body.body_id
        snap["select"] = select
        if self.on_update:
            self.on_update(snap)

    def _signature(self, body: BodyState, matches) -> str:
        parts = [
            body.body_name or "",
            ",".join(body.dss_genuses),
            str(body.bio_count),
        ]
        for m in matches:
            stage = m.progress.stage.value if m.progress else "none"
            parts.append(f"{m.species.name}:{m.certainty.value}:{stage}")
        return "|".join(parts)

    def replay_display_all_dss(self, events) -> None:
        """Process events and print every distinct DSS result (for tests / history)."""
        self.catching_up = False
        for event in events:
            self.handle(event)


def build_stack(data_dir: Path | None = None) -> tuple[Catalog, Matcher]:
    catalog = Catalog(data_dir)
    criteria = CriteriaEngine((data_dir or DATA_DIR) / "criteria")
    return catalog, Matcher(catalog, criteria)


def run_live(journal_dir: str | None = None, *, live_display: bool = True, on_update=None) -> None:
    session, watcher, path, current, caught_offset = prepare_live(
        journal_dir, live_display=live_display, on_update=on_update
    )
    follow_live(session, watcher, path, current, caught_offset)


def prepare_live(
    journal_dir: str | None = None,
    *,
    live_display: bool = True,
    on_update=None,
):
    catalog, matcher = build_stack()
    path = resolve_journal_dir(journal_dir)
    wb = None
    if HAS_OPENPYXL:
        try:
            wb = ExobioWorkbook(catalog=catalog)
            wb._save()
            if live_display:
                print_block(t("sheet_ok", path=wb.path))
        except Exception as e:
            if live_display:
                print_block(t("sheet_off", e=e))
    session = Session(catalog, matcher, live_display=live_display, workbook=wb)
    session.on_update = on_update
    watcher = JournalWatcher(path)
    session.catching_up = True
    if session.wb:
        session.wb._defer_save = True
        session.seed_hold_from_workbook()
    history = recent_journals(path)
    current = latest_journal(path)
    if live_display:
        n = len(history)
        print_block(
            t("resume", path=path, n=n, current=current.name if current else "?")
        )
    for journal in history:
        for event in watcher.iter_file(journal):
            session.handle(event)
    caught_offset = current.stat().st_size if current is not None else 0
    session.catching_up = False
    if session.wb:
        session.wb.flush()
    last = _last_interesting(session)
    if last:
        session.maybe_display(last, force=True, select=True)
    else:
        session._emit_system()
        if live_display:
            print_block(t("ready"))
    if session.on_update:
        session.on_update(session.rank_snapshot())
        session.on_update(session.explore_rank_snapshot())
        session.on_update(session.hold_snapshot())
    if live_display:
        hold = session.hold_snapshot()
        bits = []
        if hold["carto_n"]:
            bits.append(t("explo", value=fmt_m_compact(hold["carto_cr"], hold["carto_cr"])))
        if hold["n"]:
            bits.append(t("bio", value=fmt_m_compact(hold["cr"], hold["cr"]), n=hold["n"]))
        if bits:
            print_block(t("for_sale_cli") + "  ·  ".join(bits) + "\n")
    return session, watcher, path, current, caught_offset


def follow_live(session, watcher, path, current, caught_offset) -> None:
    latest = latest_journal(path)
    offset = caught_offset if latest == current else None
    for event in watcher.follow(from_start=True, start_offset=offset):
        session.handle(event)


def _is_clutter(body: BodyState) -> bool:
    name = (body.body_name or "").lower()
    if "belt cluster" in name:
        return True
    if " ring" in name or name.endswith(" ring"):
        return True
    if body.star_type or body.planet_class or body.bio_count:
        return False
    return True


def _planet_done(session: Session, body: BodyState) -> bool:
    if not body.bio_count:
        return False
    prog = session.progress.get((body.system_address, body.body_id), {})
    done = sum(1 for o in prog.values() if o.complete)
    return done >= body.bio_count


def _last_interesting(session: Session) -> BodyState | None:
    here = [
        b for b in session.bodies.values()
        if b.system_address == session.system_address and b.bio_count
    ]
    if not here:
        return None
    unfinished = [b for b in here if not _planet_done(session, b)]

    def recency(body: BodyState) -> str:
        return body.last_ts or ""

    pool = unfinished or here
    dss = [b for b in pool if b.dss_complete]
    return max(dss or pool, key=recency)


def _spectral_type(event: dict) -> str | None:
    star = event.get("StarType")
    if not star:
        return None
    sub = event.get("Subclass")
    if sub is None or sub == "":
        base = str(star)
    else:
        base = f"{star}{sub}"
    lum = event.get("Luminosity")
    if lum:
        return f"{base} {lum}"
    return base


def _parent_star_id(event: dict) -> int | None:
    for parent in event.get("Parents") or []:
        if "Star" in parent:
            return parent["Star"]
    return None


def run_replay(paths: list[Path]) -> None:
    catalog, matcher = build_stack()
    session = Session(catalog, matcher, live_display=True)
    session.replay_display_all_dss(replay_files(paths))
