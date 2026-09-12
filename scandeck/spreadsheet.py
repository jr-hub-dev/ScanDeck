"""
Gestion du classeur exobio.xlsx.

Feuille "Echantillons" — une ligne par (planète × genre DSS)
  Créée au DSS, mise à jour au ScanOrganic (Log/Sample/Analyse).

Feuille "Planetes"   — une ligne par planète DSS, vue d'ensemble.
Feuille "explo"      — systèmes avec ELW / monde aquatique / ammoniaque / phénomènes stellaires.

Clé de ligne : (SystemAddress, BodyID, genre_anglais)
  → identifie la ligne sans ambiguïté même si le journal est relu.
"""

from __future__ import annotations

import sys
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import openpyxl
    from openpyxl import load_workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.filters import AutoFilter
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

from .config import user_data_dir
from .matcher import value_tier
from .models import BodyState, OrganicProgress, ScanProgress

# ── default path ──────────────────────────────────────────────────────────
def _default_workbook_path() -> Path:
    # Personal copy next to the source tree (gitignored). Frozen / other
    # players keep the workbook in Documents or XDG.
    if not getattr(sys, "frozen", False):
        personal = Path(__file__).resolve().parents[1] / "data" / "exobio.xlsx"
        if personal.exists():
            return personal
    return user_data_dir() / "scandeck.xlsx"


DEFAULT_PATH = None  # resolved on first workbook open via _default_workbook_path()

# ── colonnes feuille Echantillons ──────────────────────────────────────────
EC_COLS = [
    "Date DSS",
    "Système",
    "Planète",
    "Type",
    "Atmosphère",
    "Température (K)",
    "Gravité (G)",
    "Étoile parente",
    "Dist. arrivée (AL)",
    "Bios",
    "Genre",
    "Espèce",
    "Variante",
    "Intérêt",
    "Échantillon",
    "Prix base (M Cr)",
    "First Logged (M Cr)",
    "Planète terminée",
    "Vendu",
]
EC_KEY_COL = "clé_interne"   # colonne cachée en fin de ligne pour retrouver la ligne

# ── colonnes feuille Planetes ──────────────────────────────────────────────
PL_COLS = [
    "Date DSS",
    "Système",
    "Planète",
    "Type",
    "Atmosphère",
    "Température (K)",
    "Gravité (G)",
    "Étoile parente",
    "Dist. arrivée (AL)",
    "Bios",
    "Genres DSS",
    "Planète terminée",
]
PL_KEY_COL = "clé_interne"

# ── colonnes feuille explo ─────────────────────────────────────────────────
EX_COLS = [
    "Date",
    "Système",
    "Planète",
    "ELW",
    "Monde aquatique",
    "Monde d'ammoniac",
    "Phénomènes stellaires",
]
EX_KEY_COL = "clé_interne"

# ── couleurs ───────────────────────────────────────────────────────────────
CLR_HEADER   = "1E3A5F"  # bleu marine
CLR_DONE     = "C6EFCE"  # vert clair
CLR_ONGOING  = "FFEB9C"  # jaune
CLR_TODO     = "FFFFFF"  # blanc

TIER_LABEL = {
    # Emoji (🔥🟢🟡🔴) : OnlyOffice ne les affiche pas → symboles BMP
    "high": "★ Flamme",
    "good": "● Bon",
    "ok":   "● Moyen",
    "low":  "● Faible",
}
TIER_FILL = {
    "high": "F4A261",  # orange flamme
    "good": "92D050",  # vert
    "ok":   "FFC000",  # orange
    "low":  "FF6B6B",  # rouge
}
TIER_FONT = {
    "high": "7A2E00",
    "good": "006100",
    "ok":   "7A4F00",
    "low":  "9C0006",
}
TIER_RANK = {"low": 0, "ok": 1, "good": 2, "high": 3}

MAX_COL_WIDTH = 26
MIN_COL_WIDTH = 10

SAMPLE_LABEL = {
    ScanProgress.NONE:    "Pas encore",
    ScanProgress.LOG:     "En cours 1/3",
    ScanProgress.SAMPLE:  "En cours 2/3",
    ScanProgress.ANALYSE: "Récupéré ✓",
}


def _mcr(value: int | None) -> float | None:
    if value is None:
        return None
    return round(value / 1_000_000, 4)


def _row_key(system_address: int | None, body_id: int | None, genus: str, catalog=None) -> str:
    canon = genus
    if catalog is not None:
        canon = catalog.canonical_genus(genus) or genus
    elif genus.lower() in {"touradon", "tussocks"}:
        canon = "Tussock"
    return f"{system_address}|{body_id}|{canon.lower()}"


def _planet_key(system_address: int | None, body_id: int | None) -> str:
    return f"{system_address}|{body_id}"


class ExobioWorkbook:
    def __init__(self, path: Path | None = None, catalog=None) -> None:
        if not HAS_OPENPYXL:
            raise ImportError(
                "openpyxl is required for the workbook.\nInstall it: pip install openpyxl"
            )
        self.path = path or _default_workbook_path()
        self._wb = self._load_or_create()
        self._ec_ws  = self._wb["Echantillons"]
        self._pl_ws  = self._wb["Planetes"]
        self._ex_ws  = self._ensure_explo_sheet()
        self.catalog = catalog
        self._defer_save = False
        self._ensure_interest_column()
        self._ensure_column(self._ec_ws, "Étoile parente", after="Gravité (G)")
        self._ensure_column(self._ec_ws, "Dist. arrivée (AL)", after="Étoile parente")
        self._ensure_column(self._pl_ws, "Étoile parente", after="Gravité (G)")
        self._ensure_column(self._pl_ws, "Dist. arrivée (AL)", after="Étoile parente")
        self._ensure_column(self._ec_ws, "Vendu", after="Planète terminée")
        self._ec_ws.column_dimensions[get_column_letter(len(EC_COLS))].hidden = False
        self._ec_ws.column_dimensions[get_column_letter(len(EC_COLS) + 1)].hidden = True
        # index en mémoire : clé → numéro de ligne (1-based)
        self._ec_index: dict[str, int] = {}
        self._pl_index: dict[str, int] = {}
        self._ex_index: dict[str, int] = {}
        self._rebuild_index()
        self._normalize_dates()
        self._backfill_interest()
        self._fit_sheets()
        self._save()

    # ── chargement / création ──────────────────────────────────────────────

    def _load_or_create(self):
        if self.path.exists():
            return load_workbook(self.path)
        wb = openpyxl.Workbook()
        # feuille par défaut renommée
        ws_ec = wb.active
        ws_ec.title = "Echantillons"
        ws_pl = wb.create_sheet("Planetes")
        ws_ex = wb.create_sheet("explo")
        self._init_sheet(ws_ec, EC_COLS + [EC_KEY_COL])
        self._init_sheet(ws_pl, PL_COLS + [PL_KEY_COL])
        self._init_sheet(ws_ex, EX_COLS + [EX_KEY_COL])
        return wb

    def _init_sheet(self, ws, cols: list[str]) -> None:
        ws.append(cols)
        for col_idx, col_name in enumerate(cols, 1):
            cell = ws.cell(1, col_idx)
            cell.font = Font(color="FFFFFF", bold=True)
            cell.fill = PatternFill("solid", fgColor=CLR_HEADER)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            # largeur auto approximative
            ws.column_dimensions[get_column_letter(col_idx)].width = max(MIN_COL_WIDTH, min(MAX_COL_WIDTH, len(col_name) + 2))
        ws.row_dimensions[1].height = 28
        ws.freeze_panes = "A2"
        # colonne clé cachée
        ws.column_dimensions[get_column_letter(len(cols))].hidden = True
        ws.auto_filter.ref = ws.dimensions

    def _ensure_explo_sheet(self):
        names = {n.casefold(): n for n in self._wb.sheetnames}
        existing = names.get("explo")
        wanted = EX_COLS + [EX_KEY_COL]
        if existing:
            ws = self._wb[existing]
            headers = [c.value for c in ws[1]]
            if headers == wanted:
                return ws
            self._wb.remove(ws)
        ws = self._wb.create_sheet("explo")
        self._init_sheet(ws, wanted)
        return ws

    # ── index en mémoire ──────────────────────────────────────────────────

    def _rebuild_index(self) -> None:
        self._ec_index = {}
        self._pl_index = {}
        self._ex_index = {}
        key_col_ec = len(EC_COLS) + 1   # dernière colonne
        key_col_pl = len(PL_COLS) + 1
        key_col_ex = len(EX_COLS) + 1
        for row in self._ec_ws.iter_rows(min_row=2, values_only=False):
            k = row[key_col_ec - 1].value
            if k:
                self._ec_index[k] = row[0].row
                if k.lower().endswith("|touradon"):
                    self._ec_index[k[: k.rfind("|") + 1] + "tussock"] = row[0].row
        for row in self._pl_ws.iter_rows(min_row=2, values_only=False):
            k = row[key_col_pl - 1].value
            if k:
                self._pl_index[k] = row[0].row
        for row in self._ex_ws.iter_rows(min_row=2, values_only=False):
            k = row[key_col_ex - 1].value
            if k:
                self._ex_index[str(k)] = row[0].row

    def _ensure_column(self, ws, name: str, *, after: str) -> None:
        headers = [c.value for c in ws[1]]
        if name in headers:
            return
        if after not in headers:
            return
        insert_at = headers.index(after) + 2
        ws.insert_cols(insert_at)
        cell = ws.cell(1, insert_at)
        cell.value = name
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = PatternFill("solid", fgColor=CLR_HEADER)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    def _ensure_interest_column(self) -> None:
        headers = [c.value for c in self._ec_ws[1]]
        if "Intérêt" in headers:
            return
        insert_at = headers.index("Variante") + 2 if "Variante" in headers else 12
        self._ec_ws.insert_cols(insert_at)
        cell = self._ec_ws.cell(1, insert_at)
        cell.value = "Intérêt"
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = PatternFill("solid", fgColor=CLR_HEADER)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    def _backfill_interest(self) -> None:
        col = {h: i + 1 for i, h in enumerate(EC_COLS)}
        if "Intérêt" not in col:
            return
        for row_num in range(2, self._ec_ws.max_row + 1):
            species = self._ec_ws.cell(row_num, col["Espèce"]).value
            genus = self._ec_ws.cell(row_num, col["Genre"]).value
            if not genus and not species:
                continue
            self._set_interest(row_num, species_name=species, genus=genus or "", catalog=self.catalog)

    def _set_interest(self, row_num: int, *, species_name, genus: str, catalog=None) -> None:
        label, tier = _interest_for(catalog or self.catalog, species_name, genus)
        col = EC_COLS.index("Intérêt") + 1
        cell = self._ec_ws.cell(row_num, col)
        cell.value = label
        self._paint_interest_cell(row_num, tier)

    def _paint_interest_cell(self, row_num: int, tier: str | None = None) -> None:
        col = EC_COLS.index("Intérêt") + 1
        cell = self._ec_ws.cell(row_num, col)
        if tier is None:
            _, tier = _tier_from_label(cell.value)
        if not tier:
            return
        cell.fill = PatternFill("solid", fgColor=TIER_FILL[tier])
        cell.font = Font(name="DejaVu Sans", bold=True, color=TIER_FONT[tier])
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    def _normalize_dates(self) -> bool:
        """Convertit les anciennes dates (texte avec heure ou datetime) en jj/mm/aaaa."""
        changed = False
        for ws in (self._ec_ws, self._pl_ws, self._ex_ws):
            for row in ws.iter_rows(min_row=2, min_col=1, max_col=1):
                cell = row[0]
                parsed = _coerce_date(cell.value)
                if parsed is None:
                    continue
                text = parsed.strftime("%d/%m/%Y")
                if cell.value != text:
                    cell.value = text
                    cell.number_format = "@"
                    changed = True
        return changed

    # ── écriture d'une ligne ───────────────────────────────────────────────

    DATE_FMT = "DD/MM/YYYY"

    def _write_row(self, ws, row_num: int, values: list[Any]) -> None:
        for col, val in enumerate(values, 1):
            cell = ws.cell(row_num, col)
            cell.value = val
            cell.alignment = Alignment(
                wrap_text=True,
                vertical="center",
                horizontal="center" if col == 1 else "left",
            )
            if col == 1:
                cell.number_format = "@"

    def _colorize_ec_row(self, row_num: int, stage: ScanProgress) -> None:
        color = {
            ScanProgress.ANALYSE: CLR_DONE,
            ScanProgress.SAMPLE:  CLR_ONGOING,
            ScanProgress.LOG:     CLR_ONGOING,
            ScanProgress.NONE:    CLR_TODO,
        }.get(stage, CLR_TODO)
        fill = PatternFill("solid", fgColor=color)
        skip = EC_COLS.index("Intérêt") + 1
        for col in range(1, len(EC_COLS) + 1):
            if col == skip:
                continue
            self._ec_ws.cell(row_num, col).fill = fill
        self._paint_interest_cell(row_num)

    # ── API principale ─────────────────────────────────────────────────────

    def on_dss(
        self,
        body: BodyState,
        timestamp: str | None = None,
        catalog=None,
    ) -> None:
        """
        Appelé quand SAASignalsFound arrive avec des genres bio.
        Crée une ligne par genre dans Echantillons (espèce vide tant que non samplée).
        Crée/màj une ligne dans Planetes.
        """
        date_str = _parse_ts(timestamp).strftime("%d/%m/%Y")
        star = body.parent_star or ""
        dist = _fmt_dist(body.distance_ls)

        # ── Feuille Planetes ──────────────────────────────────────────────
        pk = _planet_key(body.system_address, body.body_id)
        done_planet = "Non"
        if pk in self._pl_index:
            done_col = PL_COLS.index("Planète terminée") + 1
            done_planet = self._pl_ws.cell(self._pl_index[pk], done_col).value or "Non"
        pl_row = [
            date_str,
            body.system_name,
            body.body_name,
            _short_type(body.planet_class),
            body.atmosphere_type or "",
            round(body.temperature_k, 1) if body.temperature_k else "",
            round(body.gravity_g, 3) if body.gravity_g else "",
            star,
            dist,
            body.bio_count or "",
            ", ".join(body.dss_genuses),
            done_planet,
            pk,
        ]
        if pk in self._pl_index:
            self._write_row(self._pl_ws, self._pl_index[pk], pl_row)
        else:
            self._pl_ws.append([None] * len(pl_row))
            self._pl_index[pk] = self._pl_ws.max_row
            self._write_row(self._pl_ws, self._pl_index[pk], pl_row)

        # ── Feuille Echantillons — une ligne par genre ────────────────────
        for genus in body.dss_genuses:
            rk = _row_key(body.system_address, body.body_id, genus, catalog or self.catalog)
            shown_genus = (catalog or self.catalog).display_genus(genus) if (catalog or self.catalog) else genus
            if rk in self._ec_index:
                self._patch_star_dist(self._ec_ws, self._ec_index[rk], star, dist)
                continue   # ligne déjà créée (ex: replay double SAASignalsFound)

            # prix min/max du genre si catalog disponible
            price_base = ""
            price_fl   = ""
            if catalog:
                species_list = catalog.species_for_genus(genus)
                if species_list:
                    vals = sorted(s.value_cr for s in species_list)
                    # on met la fourchette "min - max" en texte si plusieurs espèces possibles
                    if len(vals) == 1:
                        price_base = _mcr(vals[0])
                        price_fl   = _mcr(vals[0] * 5)
                    else:
                        price_base = f"{_mcr(vals[0])} – {_mcr(vals[-1])}"
                        price_fl   = f"{_mcr(vals[0]*5)} – {_mcr(vals[-1]*5)}"

            label, _tier = _interest_for(catalog or self.catalog, "", genus)
            cat = catalog or self.catalog
            shown_genus = cat.display_genus(genus) if cat else genus
            ec_row = [
                date_str,
                body.system_name,
                body.body_name,
                _short_type(body.planet_class),
                body.atmosphere_type or "",
                round(body.temperature_k, 1) if body.temperature_k else "",
                round(body.gravity_g, 3) if body.gravity_g else "",
                star,
                dist,
                body.bio_count or "",
                shown_genus,
                "",           # Espèce — vide
                "",           # Variante — vide
                label,        # Intérêt (meilleur du genre tant que l'espèce n'est pas connue)
                SAMPLE_LABEL[ScanProgress.NONE],
                price_base,
                price_fl,
                "Non",
                "Non",
                rk,
            ]
            self._ec_ws.append([None] * len(ec_row))
            row_num = self._ec_ws.max_row
            self._ec_index[rk] = row_num
            self._write_row(self._ec_ws, row_num, ec_row)
            self._colorize_ec_row(row_num, ScanProgress.NONE)

        self._save()

    def _patch_star_dist(self, ws, row_num: int, star: str, dist) -> None:
        headers = [c.value for c in ws[1]]
        if "Étoile parente" in headers:
            ws.cell(row_num, headers.index("Étoile parente") + 1).value = star
        if "Dist. arrivée (AL)" in headers:
            ws.cell(row_num, headers.index("Dist. arrivée (AL)") + 1).value = dist

    def on_scan_organic(
        self,
        body: BodyState,
        genus: str,
        species_name: str,
        variant: str | None,
        stage: ScanProgress,
        catalog=None,
    ) -> None:
        """
        Appelé à chaque ScanOrganic (Log, Sample, Analyse).
        Met à jour la ligne correspondante dans Echantillons.
        Si Analyse : marque la planète terminée si tous les bios sont faits.
        """
        rk = _row_key(body.system_address, body.body_id, genus, catalog or self.catalog)
        row_num = self._ec_index.get(rk)
        if row_num is None:
            # ancienne clé journal FR (Touradon) avant normalisation
            rk_raw = f"{body.system_address}|{body.body_id}|{(genus or '').lower()}"
            row_num = self._ec_index.get(rk_raw)
            if row_num is not None:
                rk = rk_raw
        if row_num is None:
            # la ligne n'existe pas encore (ex: sampler avant DSS) → on crée
            self.on_dss(body, catalog=catalog)
            row_num = self._ec_index.get(rk)
            if row_num is None:
                return

        ws = self._ec_ws
        col = {h: i+1 for i, h in enumerate(EC_COLS)}
        cat = catalog or self.catalog
        shown_species = cat.display_species(species_name) if cat else species_name
        shown_genus = cat.display_genus(genus) if cat else genus

        # prix exact dès que l'espèce est identifiée
        price_base = ""
        price_fl   = ""
        if catalog and species_name:
            sp = catalog.get(species_name)
            if sp:
                price_base = _mcr(sp.value_cr)
                price_fl   = _mcr(sp.first_logged_cr)

        ws.cell(row_num, col["Genre"]).value           = shown_genus or ws.cell(row_num, col["Genre"]).value
        ws.cell(row_num, col["Espèce"]).value          = shown_species or ws.cell(row_num, col["Espèce"]).value
        ws.cell(row_num, col["Variante"]).value        = variant or ws.cell(row_num, col["Variante"]).value
        ws.cell(row_num, col["Échantillon"]).value     = SAMPLE_LABEL[stage]
        if stage == ScanProgress.ANALYSE and "Vendu" in col:
            current = (ws.cell(row_num, col["Vendu"]).value or "").strip().lower()
            if current not in {"oui", "yes"}:
                ws.cell(row_num, col["Vendu"]).value = "Non"
        if price_base:
            ws.cell(row_num, col["Prix base (M Cr)"]).value   = price_base
            ws.cell(row_num, col["First Logged (M Cr)"]).value = price_fl
        self._set_interest(
            row_num,
            species_name=ws.cell(row_num, col["Espèce"]).value,
            genus=genus,
            catalog=catalog,
        )

        self._colorize_ec_row(row_num, stage)
        self._save()

    def mark_planet_done(self, body: BodyState) -> None:
        """Marque 'Planète terminée = Oui' dans les deux feuilles."""
        pk = _planet_key(body.system_address, body.body_id)
        pl_row = self._pl_index.get(pk)
        if pl_row:
            col_done = len(PL_COLS)   # "Planète terminée" est la dernière colonne avant clé
            self._pl_ws.cell(pl_row, col_done).value = "Oui"
            self._pl_ws.cell(pl_row, col_done).fill = PatternFill("solid", fgColor=CLR_DONE)

        col_done_ec = EC_COLS.index("Planète terminée") + 1
        for genus in body.dss_genuses:
            rk = _row_key(body.system_address, body.body_id, genus, self.catalog)
            row_num = self._ec_index.get(rk)
            if row_num:
                self._ec_ws.cell(row_num, col_done_ec).value = "Oui"

        self._save()

    def unsold_hold(self, catalog=None) -> tuple[dict[tuple, int], dict[tuple, int]]:
        """Analyses pas encore vendues : base et First logged."""
        cat = catalog or self.catalog
        col = {h: i + 1 for i, h in enumerate(EC_COLS) if h}
        if "Échantillon" not in col or "Espèce" not in col:
            return {}, {}
        sold_col = col.get("Vendu")
        key_col = len(EC_COLS) + 1
        done_label = SAMPLE_LABEL[ScanProgress.ANALYSE]
        hold: dict[tuple, int] = {}
        hold_first: dict[tuple, int] = {}
        for row_num in range(2, self._ec_ws.max_row + 1):
            stage = self._ec_ws.cell(row_num, col["Échantillon"]).value
            if stage != done_label:
                continue
            if sold_col:
                sold = (self._ec_ws.cell(row_num, sold_col).value or "").strip().lower()
                if sold not in {"non", "no"}:
                    continue
            species_shown = (self._ec_ws.cell(row_num, col["Espèce"]).value or "").strip()
            if not species_shown:
                continue
            name = species_shown.replace("Touradon", "Tussock")
            sp = cat.get(name) if cat else None
            if sp is None and cat:
                sp = cat.get(species_shown)
            value = sp.value_cr if sp else 0
            first = sp.first_logged_cr if sp else 0
            raw_key = self._ec_ws.cell(row_num, key_col).value or ""
            parts = str(raw_key).split("|")
            try:
                address = int(parts[0]) if parts[0] not in {"", "None"} else None
                body_id = int(parts[1]) if len(parts) > 1 and parts[1] not in {"", "None"} else None
            except ValueError:
                address, body_id = None, None
            species_name = sp.name if sp else name
            key = (address, body_id, species_name)
            hold[key] = value
            hold_first[key] = first
        return hold, hold_first

    def mark_all_sold(self) -> None:
        """Vista Genomics vend tout le stock d'un coup."""
        col = {h: i + 1 for i, h in enumerate(EC_COLS) if h}
        if "Vendu" not in col or "Échantillon" not in col:
            return
        done_label = SAMPLE_LABEL[ScanProgress.ANALYSE]
        changed = False
        for row_num in range(2, self._ec_ws.max_row + 1):
            if self._ec_ws.cell(row_num, col["Échantillon"]).value != done_label:
                continue
            cell = self._ec_ws.cell(row_num, col["Vendu"])
            if (cell.value or "").strip().lower() in {"oui", "yes"}:
                continue
            cell.value = "Oui"
            changed = True
        if changed:
            self._save()

    def upsert_explo_find(
        self,
        *,
        key: str,
        timestamp: str | None = None,
        system: str,
        planet: str = "",
        elw: int | None = None,
        ww: int | None = None,
        aw: int | None = None,
        nsp: str = "",
    ) -> None:
        """Une ligne par trouvaille (planète rare ou phénomène), filtrable."""
        if not elw and not ww and not aw and not (nsp or "").strip():
            return
        date_str = _parse_ts(timestamp).strftime("%d/%m/%Y")
        values = [
            date_str,
            system,
            planet or "",
            elw or "",
            ww or "",
            aw or "",
            (nsp or "").strip(),
            key,
        ]
        if key in self._ex_index:
            row_num = self._ex_index[key]
            previous = self._ex_ws.cell(row_num, 1).value
            if previous:
                values[0] = previous
            self._write_row(self._ex_ws, row_num, values)
        else:
            self._ex_ws.append([None] * len(values))
            row_num = self._ex_ws.max_row
            self._ex_index[key] = row_num
            self._write_row(self._ex_ws, row_num, values)
        self._ex_ws.auto_filter.ref = self._ex_ws.dimensions
        self._save()

    # ── sauvegarde ────────────────────────────────────────────────────────

    def _save(self) -> None:
        if self._defer_save:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fit_sheets()
        self._wb.save(self.path)

    def flush(self) -> None:
        self._defer_save = False
        self._save()

    def _fit_sheets(self) -> None:
        self._fit_sheet(self._ec_ws, len(EC_COLS))
        self._fit_sheet(self._pl_ws, len(PL_COLS))
        self._fit_sheet(self._ex_ws, len(EX_COLS))

    def _fit_sheet(self, ws, visible_cols: int) -> None:
        longest = [0] * visible_cols
        last_row = max(ws.max_row, 1)
        for row in ws.iter_rows(min_row=1, max_row=last_row, max_col=visible_cols):
            for i, cell in enumerate(row):
                text = "" if cell.value is None else str(cell.value)
                line_len = max((len(part) for part in text.splitlines()), default=0)
                if line_len > longest[i]:
                    longest[i] = line_len
                is_header = cell.row == 1
                cell.alignment = Alignment(
                    wrap_text=True,
                    vertical="center",
                    horizontal="center" if is_header else "left",
                )
        for i, length in enumerate(longest, 1):
            width = min(MAX_COL_WIDTH, max(MIN_COL_WIDTH, length + 2.5))
            ws.column_dimensions[get_column_letter(i)].width = width
        for r in range(1, last_row + 1):
            lines = 1
            for c in range(1, visible_cols + 1):
                text = "" if ws.cell(r, c).value is None else str(ws.cell(r, c).value)
                col_w = ws.column_dimensions[get_column_letter(c)].width or MIN_COL_WIDTH
                usable = max(6, int(col_w) - 2)
                need = _wrapped_line_count(text, usable)
                if need > lines:
                    lines = need
            # ~18 pt par ligne + marge, sans plafond trop bas
            height = 20 * lines + 8 if r == 1 else 18 * lines + 6
            ws.row_dimensions[r].height = max(20, min(140, height))
        ws.freeze_panes = "A2"
        if last_row >= 1:
            ws.auto_filter.ref = f"A1:{get_column_letter(visible_cols)}{last_row}"


# ── helpers ────────────────────────────────────────────────────────────────

def _parse_ts(ts: str | None):
    """Retourne un objet date Python (pas une chaîne) pour qu'openpyxl applique le format cellule."""
    parsed = _coerce_date(ts)
    if parsed is not None:
        return parsed
    return datetime.now(timezone.utc).date()


def _coerce_date(value):
    """Accepte date, datetime, ou chaîne journal / ancienne cellule Excel."""
    if value is None:
        return None
    if hasattr(value, "hour") and hasattr(value, "date"):
        return value.date()
    if hasattr(value, "year") and not hasattr(value, "hour"):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _interest_for(catalog, species_name, genus: str) -> tuple[str, str | None]:
    if catalog is None:
        return "", None
    name = (species_name or "").strip()
    if name:
        sp = catalog.get(name)
        if sp:
            tier = value_tier(sp)
            return TIER_LABEL[tier], tier
    if genus:
        species_list = catalog.species_for_genus(genus)
        if species_list:
            best = max(species_list, key=lambda s: (TIER_RANK[value_tier(s)], s.value_cr))
            tier = value_tier(best)
            if len({value_tier(s) for s in species_list}) > 1:
                return f"{TIER_LABEL[tier]} (max)", tier
            return TIER_LABEL[tier], tier
    return "", None


def _tier_from_label(value) -> tuple[str, str | None]:
    text = str(value or "")
    lowered = text.lower()
    if "flamme" in lowered or "haute" in lowered or "🔥" in text:
        return text, "high"
    if "moyen" in lowered or "🟡" in text:
        return text, "ok"
    if "faible" in lowered or "🔴" in text:
        return text, "low"
    if "bon" in lowered or "🟢" in text:
        return text, "good"
    return text, None


def _fmt_dist(distance_ls: float | None):
    if distance_ls is None:
        return ""
    if distance_ls >= 100:
        return round(distance_ls)
    return round(distance_ls, 1)


def _wrapped_line_count(text: str, width: int) -> int:
    """Nombre de lignes après retour à la ligne (coupure sur les mots)."""
    width = max(4, width)
    if not text:
        return 1
    total = 0
    for para in str(text).splitlines() or [""]:
        if not para.strip():
            total += 1
            continue
        line_len = 0
        para_lines = 1
        for word in para.split():
            wlen = len(word)
            chunks = max(1, (wlen + width - 1) // width)
            if line_len == 0:
                para_lines += chunks - 1
                line_len = wlen if chunks == 1 else wlen % width or width
                continue
            if line_len + 1 + wlen <= width:
                line_len += 1 + wlen
            else:
                para_lines += chunks
                line_len = wlen if chunks == 1 else wlen % width or width
        total += para_lines
    return max(1, total)


def _short_type(planet_class: str | None) -> str:
    return {
        "High metal content body": "HMC",
        "Rocky body":              "Rocky",
        "Rocky ice body":          "Rocky Ice",
        "Icy body":                "Icy",
        "Metal rich body":         "Metal Rich",
    }.get(planet_class or "", planet_class or "")
