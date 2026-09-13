"""Petit HUD sombre, toujours au-dessus, alimenté par le journal."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import filedialog, font as tkfont
from pathlib import Path

from .app import follow_live, prepare_live
from .config import load as load_config, save as save_config
from .eddn import get_hub
from .i18n import is_auto, lang, t
from .inara import sync as inara_sync
from .journal import guessed_journal_dir
from .macros import (
    HOLD_TAP_MS,
    HotkeyGrabber,
    binds_map,
    delete_macro,
    format_hold_s,
    hotkey_in_use,
    is_playing,
    load_macros,
    play_macro,
    pretty_key,
    upsert_macro,
)
from . import __version__
from .paths import resource_root
from .ranks import EXPLORE_RANKS, RANKS, fmt_credits, fmt_threshold, rank_short
from .scan_value import fmt_scan_cr
from .update import RELEASES_URL, newer_release

# Palette EDHM Azure Sky : cyan HUD, fond quasi noir, orange seulement en alerte.
BG = "#05080c"
CARD = "#0b1218"
CARD2 = "#101820"
TEXT = "#d6f6ff"
MUTED = "#5e8494"
LINE = "#123038"
CYAN = "#00d4f0"
CYAN_DIM = "#2a8a9c"
CYAN_DEEP = "#0c2a36"
CYAN_HI = "#9af6ff"
WARN = "#ff8c00"
READY = "#92d050"
ALERT_BG = "#2a1808"
ALERT_FG = "#ffc4a0"
# Pastilles d’intérêt (espèces) — distinctes du cyan HUD.
TIER_BAR = {
    "high": "#ff7f11",
    "good": "#92d050",
    "ok": "#ffc000",
    "low": "#ff6b6b",
    "muted": MUTED,
}
FONT = "Fira Sans Condensed"
SCROLL_W = 8
# Largeurs fixes : explo à gauche, macros à droite, exo au centre (le reste).
LEFT_COL_W = 400
MACRO_COL_W = 280


def _pick_font(root: tk.Tk) -> None:
    global FONT
    available = {name.lower() for name in tkfont.families(root)}
    for name in ("Fira Sans Condensed", "DejaVu Sans Condensed", "DejaVu Sans", "Segoe UI", "Arial"):
        if name.lower() in available:
            FONT = name
            return


def _font(size: int, weight: str = "normal") -> tuple:
    return (FONT, size, weight)


def _make_hold_line(parent, *, right: bool, pady, with_count: bool) -> dict:
    row = tk.Frame(parent, bg=BG)
    row.pack(fill="x", pady=pady)
    kw = dict(fg=MUTED, bg=BG, font=_font(8, "bold"))
    prefix = tk.Label(row, **kw)
    base = tk.Label(row, **kw)
    dash = tk.Label(row, **kw)
    fl = tk.Label(row, **kw)
    count = tk.Label(row, **kw) if with_count else None
    if right:
        if count is not None:
            count.pack(side="right")
        fl.pack(side="right")
        dash.pack(side="right")
        base.pack(side="right")
        prefix.pack(side="right")
    else:
        prefix.pack(side="left")
        base.pack(side="left")
        dash.pack(side="left")
        fl.pack(side="left")
        if count is not None:
            count.pack(side="left")
    return {"prefix": prefix, "base": base, "dash": dash, "fl": fl, "count": count}


def _outline_btn(parent, text: str, command, *, padx: int = 10, pady: int = 5) -> tk.Label:
    """Bouton cyan (pied de HUD, éditeur de macro). padx/pady = taille du clic."""
    wrap = tk.Frame(parent, bg=CYAN)
    wrap.pack(side="left", padx=(0, 8))
    lbl = tk.Label(
        wrap, text=text, fg=CYAN, bg=BG,
        font=_font(9, "bold"), cursor="hand2",
        padx=padx, pady=pady,
    )
    lbl.pack(padx=1, pady=1)
    lbl.bind("<Button-1>", lambda _e: command())
    lbl.bind("<Enter>", lambda _e: lbl.config(fg=TEXT))
    lbl.bind("<Leave>", lambda _e: lbl.config(fg=CYAN))
    return lbl


def _relaunch() -> None:
    if getattr(sys, "frozen", False):
        os.execv(sys.executable, [sys.executable])
        return
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    os.execv(sys.executable, [sys.executable, "-m", "scandeck"])


class ThinPane:
    """Canvas + barre de scroll cyan, masquée si tout tient à l'écran."""

    def __init__(self, parent) -> None:
        self.wrap = tk.Frame(parent, bg=BG)
        self.canvas = tk.Canvas(self.wrap, bg=BG, highlightthickness=0, bd=0)
        self._scroll = tk.Canvas(
            self.wrap, width=SCROLL_W, bg=BG, highlightthickness=0, bd=0,
            cursor="sb_v_double_arrow",
        )
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self._first = 0.0
        self._last = 1.0
        self._drag_off: float | None = None
        self._hover = False
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.configure(yscrollcommand=self._on_yview)
        self._scroll.bind("<Button-1>", self._scroll_down)
        self._scroll.bind("<B1-Motion>", self._scroll_drag)
        self._scroll.bind("<ButtonRelease-1>", lambda _e: self._set_drag(None))
        self._scroll.bind("<Configure>", lambda _e: self._draw(self._hover))
        self._scroll.bind("<Enter>", lambda _e: self._draw(hover=True))
        self._scroll.bind("<Leave>", lambda _e: self._draw(hover=False))
    def _on_inner(self, _e=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all") or (0, 0, 0, 0))
        first, last = self.canvas.yview()
        self._on_yview(first, last)

    def _on_canvas(self, event) -> None:
        self.canvas.itemconfigure(self._win, width=max(event.width, 1))
        first, last = self.canvas.yview()
        self._on_yview(first, last)

    def needed(self) -> bool:
        bbox = self.canvas.bbox("all")
        if not bbox:
            return False
        view = max(self.canvas.winfo_height(), 1)
        return (bbox[3] - bbox[1]) > view + 8

    def wheel(self, steps: int) -> None:
        if not self.needed():
            return
        self.canvas.yview_scroll(steps, "units")

    def _set_drag(self, value: float | None) -> None:
        self._drag_off = value

    def _on_yview(self, first, last) -> None:
        self._first, self._last = float(first), float(last)
        self._draw(self._hover)

    def _thumb_geom(self) -> tuple[float, float, float, float, float]:
        h = max(self._scroll.winfo_height(), 1)
        pad = 8.0
        track = max(h - 2 * pad, 1.0)
        span = min(max(self._last - self._first, 0.08), 1.0)
        thumb_h = max(24.0, min(track * span, track * 0.85))
        travel = max(track - thumb_h, 1.0)
        t = self._first / max(1.0 - (self._last - self._first), 1e-6)
        t = max(0.0, min(1.0, t))
        return pad, track, thumb_h, pad + t * travel, span

    def _draw(self, hover: bool = False) -> None:
        self._hover = hover
        if not self.needed():
            if self._scroll.winfo_ismapped():
                self._scroll.pack_forget()
            self._scroll.delete("all")
            return
        if not self._scroll.winfo_ismapped():
            self._scroll.pack(side="right", fill="y", padx=(0, 1))
        self._scroll.delete("all")
        h = max(self._scroll.winfo_height(), 1)
        pad, _track, thumb_h, thumb_y, _span = self._thumb_geom()
        mid = SCROLL_W / 2
        self._scroll.create_line(mid, pad, mid, h - pad, fill=CYAN_DEEP, width=1)
        fill = CYAN if hover or self._drag_off is not None else CYAN_DIM
        self._scroll.create_rectangle(
            mid - 2, thumb_y, mid + 2, thumb_y + thumb_h,
            fill=fill, outline="",
        )

    def _scroll_down(self, event) -> None:
        _pad, _track, thumb_h, thumb_y, _span = self._thumb_geom()
        if thumb_y <= event.y <= thumb_y + thumb_h:
            self._drag_off = event.y - thumb_y
        else:
            self._drag_off = thumb_h / 2
            self._scroll_to_y(event.y)
        self._draw(hover=True)

    def _scroll_drag(self, event) -> None:
        if self._drag_off is None:
            self._drag_off = 0
        self._scroll_to_y(event.y)

    def _scroll_to_y(self, y: float) -> None:
        pad, track, thumb_h, _ty, span = self._thumb_geom()
        travel = max(track - thumb_h, 1.0)
        t = (y - pad - (self._drag_off or 0)) / travel
        first = max(0.0, min(1.0, t)) * max(1.0 - span, 0.0)
        self.canvas.yview_moveto(first)


class ScanDeckHud:
    def __init__(self, journal_dir: str | None = None) -> None:
        self.q: queue.Queue = queue.Queue()
        self.workbook_path: Path | None = None
        self._snap: dict = {}
        self._sys: dict = {}
        self._sys_name = ""
        self._details: dict = {}
        self._selected_id = None
        self._list_sig = None
        self._first = 0.0
        self._last = 1.0
        self._drag_off: float | None = None
        self._hold_snap: dict = {}
        self.root = tk.Tk()
        self.root.title("ScanDeck")
        self._apply_icon()
        _pick_font(self.root)
        self.root.configure(bg=BG)
        self.root.geometry("1420x780")
        self.root.minsize(1280, 600)
        self.root.attributes("-topmost", True)

        edge = tk.Frame(self.root, bg=CYAN, width=2)
        edge.pack(side="left", fill="y")

        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True)

        heads = tk.Frame(main, bg=BG)
        heads.pack(fill="x")
        # Trois colonnes dès l’en-tête, avec le même trait que explo | exo.

        left_heads = tk.Frame(heads, bg=BG, width=LEFT_COL_W)
        left_heads.pack(side="left", fill="y")
        left_heads.pack_propagate(False)

        left_head = tk.Frame(left_heads, bg=BG)
        left_head.pack(fill="x", padx=10, pady=(12, 0))
        sys_row = tk.Frame(left_head, bg=BG)
        sys_row.pack(fill="x")
        self.sys_lbl = tk.Label(
            sys_row, text="SCANDECK", fg=CYAN, bg=BG,
            font=_font(12, "bold"), anchor="w", wraplength=200, justify="left",
        )
        self.sys_lbl.pack(side="left", fill="x", expand=True)
        self._copy_btn(sys_row, "sys")
        self.sys_meta = tk.Label(
            left_head, text="", fg=MUTED, bg=BG,
            font=_font(8), anchor="w", wraplength=220, justify="left",
        )
        self.sys_meta.pack(fill="x", pady=(2, 8))
        tk.Frame(left_head, bg=CYAN, height=1).pack(fill="x")
        self._carto_hold = _make_hold_line(left_head, right=False, pady=(8, 0), with_count=True)
        self._carto_hold["prefix"].config(text=f"{t('for_sale_carto')}  —")
        self._carto_fc = _make_hold_line(left_head, right=False, pady=(1, 0), with_count=False)

        tk.Frame(heads, bg=LINE, width=1).pack(side="left", fill="y")

        self._macro_heads = tk.Frame(heads, bg=BG, width=MACRO_COL_W)
        self._macro_heads.pack(side="right", fill="y")
        self._macro_heads.pack_propagate(False)
        tk.Frame(heads, bg=LINE, width=1).pack(side="right", fill="y")
        macro_head = tk.Frame(self._macro_heads, bg=BG)
        macro_head.pack(fill="x", padx=12, pady=(12, 0))
        tk.Label(
            macro_head, text=t("macros_title"), fg=CYAN, bg=BG,
            font=_font(12, "bold"), anchor="w",
        ).pack(fill="x")
        tk.Label(
            macro_head, text=" ", fg=BG, bg=BG,
            font=_font(8), anchor="w",
        ).pack(fill="x", pady=(2, 8))
        tk.Frame(macro_head, bg=CYAN, height=1).pack(fill="x")

        self._right_top = tk.Frame(heads, bg=BG)
        self._right_top.pack(side="left", fill="both", expand=True)
        self._right_top.bind("<Configure>", self._on_right_configure)

        self._header = tk.Frame(self._right_top, bg=BG)
        self._header.pack(fill="x", padx=16, pady=(12, 0))

        body_row = tk.Frame(self._header, bg=BG)
        body_row.pack(fill="x")
        self.body_lbl = tk.Label(
            body_row, text=t("waiting_dss"), fg=MUTED, bg=BG,
            font=_font(12), anchor="w", wraplength=400, justify="left",
        )
        self.body_lbl.pack(side="left", fill="x", expand=True)
        self._copy_btn(body_row, "body")
        self.meta_lbl = tk.Label(
            self._header, text="", fg=MUTED, bg=BG,
            font=_font(9), anchor="w", wraplength=420, justify="left",
        )
        self.meta_lbl.pack(fill="x", pady=(2, 8))
        tk.Frame(self._header, bg=CYAN, height=1).pack(fill="x")
        self._bio_hold = _make_hold_line(self._header, right=True, pady=(8, 0), with_count=True)
        self._bio_hold["prefix"].config(text=f"{t('for_sale_bio')}  —")
        self._bio_fc = _make_hold_line(self._header, right=True, pady=(1, 0), with_count=False)

        self.scan_lbl = tk.Label(
            self._right_top, text="", fg=CYAN, bg=BG,
            font=_font(10, "bold"), anchor="w",
        )
        self.scan_lbl.pack(fill="x", padx=16, pady=(10, 0))

        self.alert_lbl = tk.Label(
            self._right_top, text="", fg=ALERT_FG, bg=ALERT_BG,
            font=_font(10, "bold"), pady=6,
        )

        self.verdict_lbl = tk.Label(
            self._right_top, text="", fg=CYAN, bg=BG,
            font=_font(13, "bold"), anchor="w", wraplength=420, justify="left",
        )
        self.verdict_lbl.pack(fill="x", padx=16, pady=(6, 0))
        self.verdict_sub = tk.Label(
            self._right_top, text="", fg=MUTED, bg=BG,
            font=_font(9), anchor="w", wraplength=420, justify="left",
        )
        self.verdict_sub.pack(fill="x", padx=16, pady=(0, 10))

        band = tk.Frame(main, bg=BG)
        band.pack(fill="both", expand=True)

        self._macro_col = tk.Frame(band, bg=BG, width=MACRO_COL_W)
        self._macro_col.pack(side="right", fill="y")
        self._macro_col.pack_propagate(False)
        tk.Frame(band, bg=LINE, width=1).pack(side="right", fill="y")
        self._build_macro_col()

        self._left = tk.Frame(band, bg=BG, width=LEFT_COL_W)
        self._left.pack(side="left", fill="y")
        self._left.pack_propagate(False)

        self.explore_rail = RankRail(self._left, mirror=True, ranks=EXPLORE_RANKS)
        self.explore_rail.pack(side="left", fill="y", padx=(2, 0))
        self._left_pane = ThinPane(self._left)
        self._left_pane.wrap.pack(side="left", fill="both", expand=True, pady=4)
        self._left_list = self._left_pane.inner

        tk.Frame(band, bg=LINE, width=1).pack(side="left", fill="y")

        self._right = tk.Frame(band, bg=BG)
        self._right.pack(side="left", fill="both", expand=True)

        canvas_wrap = tk.Frame(self._right, bg=BG)
        canvas_wrap.pack(fill="both", expand=True, padx=(10, 0))
        self.canvas = tk.Canvas(canvas_wrap, bg=BG, highlightthickness=0, bd=0)
        self.rail = RankRail(canvas_wrap)
        self.rail.pack(side="right", fill="y", padx=(2, 2))
        self._scroll = tk.Canvas(
            canvas_wrap, width=SCROLL_W, bg=BG, highlightthickness=0, bd=0,
            cursor="sb_v_double_arrow",
        )
        self.canvas.configure(yscrollcommand=self._on_yview)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.list_fr = tk.Frame(self.canvas, bg=BG)
        self._win = self.canvas.create_window((0, 0), window=self.list_fr, anchor="nw")
        self.list_fr.bind("<Configure>", self._on_list_configure)
        self.canvas.bind("<Configure>", self._on_canvas_width)
        self.root.bind_all("<MouseWheel>", self._on_wheel)
        self.root.bind_all("<Button-4>", lambda e: self._on_button_wheel(e, -1))
        self.root.bind_all("<Button-5>", lambda e: self._on_button_wheel(e, 1))
        self._scroll.bind("<Button-1>", self._scroll_down)
        self._scroll.bind("<B1-Motion>", self._scroll_drag)
        self._scroll.bind("<ButtonRelease-1>", lambda _e: self._set_drag(None))
        self._scroll.bind("<Configure>", lambda _e: self._draw_scroll(self._scroll_hover))
        self._scroll.bind("<Enter>", lambda _e: self._draw_scroll(hover=True))
        self._scroll.bind("<Leave>", lambda _e: self._draw_scroll(hover=False))
        self._scroll.bind("<Button-4>", lambda e: self._wheel(-1))
        self._scroll.bind("<Button-5>", lambda e: self._wheel(1))
        self._scroll_hover = False

        foot = tk.Frame(self.root, bg=BG)
        foot.pack(fill="x", padx=12, pady=8)
        tk.Frame(foot, bg=CYAN_DIM, height=1).pack(fill="x", pady=(0, 8))
        self._sheet_btn = _outline_btn(foot, t("open_sheet"), self._open_xlsx)
        self._opt_btn = _outline_btn(foot, t("options"), self._open_options)
        self._eddn_btn = _outline_btn(foot, t("eddn_logs"), self._open_eddn_log)
        self._inara_btn = _outline_btn(foot, t("inara_send"), self._send_inara)
        self._ver_lbl = tk.Label(
            foot, text=t("hud_version", version=__version__),
            fg=MUTED, bg=BG, font=_font(8),
        )
        self._ver_lbl.pack(side="left", padx=(4, 0))
        self._upd_lbl = tk.Label(
            foot, text="", fg=CYAN, bg=BG, font=_font(8, "bold"), cursor="hand2",
        )
        self._upd_lbl.pack(side="left", padx=(10, 0))
        self._upd_lbl.bind("<Button-1>", lambda _e: webbrowser.open(RELEASES_URL))
        self._upd_lbl.bind("<Enter>", lambda _e: self._upd_lbl.config(fg=TEXT) if self._upd_lbl.cget("text") else None)
        self._upd_lbl.bind("<Leave>", lambda _e: self._upd_lbl.config(fg=CYAN))
        self.status_lbl = tk.Label(foot, text=t("starting"), fg=MUTED, bg=BG, font=_font(8))
        self.status_lbl.pack(side="right")

        self._start_watcher(journal_dir)
        self.root.after(150, self._drain)
        self._start_update_check()
        # Touche de lancement : callback sur le thread Tk (le grabber tourne à part).
        self._hotkeys = HotkeyGrabber(lambda row: self.root.after(0, lambda r=row: self._macro_play(r)))
        self._hotkeys.start()
        self._sync_macro_hotkeys()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_icon(self) -> None:
        png = resource_root() / "data" / "icon.png"
        ico = resource_root() / "data" / "icon.ico"
        if png.exists():
            try:
                img = tk.PhotoImage(file=str(png))
                self.root.iconphoto(True, img)
                self._icon_img = img
            except tk.TclError:
                self._icon_img = None
        if sys.platform == "win32" and ico.exists():
            try:
                self.root.iconbitmap(str(ico))
            except tk.TclError:
                pass

    def _copy_btn(self, parent, kind: str) -> None:
        lbl = tk.Label(
            parent, text=" ⎘ ", fg=CYAN_DIM, bg=BG,
            font=_font(10), cursor="hand2",
        )
        lbl.pack(side="right", padx=(6, 0))
        lbl.bind("<Button-1>", lambda _e: self._copy(kind))
        lbl.bind("<Enter>", lambda _e: lbl.config(fg=CYAN))
        lbl.bind("<Leave>", lambda _e: lbl.config(fg=CYAN_DIM))

    def _copy(self, kind: str) -> None:
        if kind == "sys":
            text = (self._sys.get("system") or self._snap.get("system")) or ""
        else:
            text = (self._snap.get("body") or "")
        if not text:
            self.status_lbl.config(text=t("nothing_to_copy"))
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
        self.status_lbl.config(text=t("copied", text=text))

    def _hold_fg(self, credits: int, remain) -> str:
        if remain is not None and remain > 0 and credits >= remain:
            return READY
        return CYAN

    def _paint_hold_line(
        self,
        line: dict,
        *,
        prefix: str,
        empty: bool,
        hide: bool = False,
        base_cr: int = 0,
        fl_cr: int = 0,
        remain=None,
        n: int | None = None,
    ) -> None:
        count = line["count"]
        if empty:
            line["prefix"].config(text="" if hide else f"{prefix}  —", fg=MUTED)
            line["base"].config(text="", fg=MUTED)
            line["dash"].config(text="", fg=MUTED)
            line["fl"].config(text="", fg=MUTED)
            if count is not None:
                count.config(text="", fg=MUTED)
            return
        line["prefix"].config(text=f"{prefix}  ", fg=CYAN)
        line["base"].config(text=fmt_scan_cr(base_cr), fg=self._hold_fg(base_cr, remain))
        line["dash"].config(text=" - ", fg=CYAN)
        line["fl"].config(text=fmt_scan_cr(fl_cr), fg=self._hold_fg(fl_cr, remain))
        if count is not None:
            count.config(text=f"  ·  {n}", fg=CYAN)

    def _render_hold(self, snap: dict) -> None:
        carto_n = int(snap.get("carto_n") or 0)
        carto_cr = int(snap.get("carto_cr") or 0)
        carto_fl = int(snap.get("carto_first_cr") or 0)
        remain_ex = self.explore_rail.snap.get("remain")
        if carto_n <= 0:
            self._paint_hold_line(self._carto_hold, prefix=t("for_sale_carto"), empty=True)
            self._paint_hold_line(self._carto_fc, prefix=t("for_sale_carto_fc"), empty=True, hide=True)
        else:
            self._paint_hold_line(
                self._carto_hold,
                prefix=t("for_sale_carto"),
                empty=False,
                base_cr=carto_cr,
                fl_cr=carto_fl,
                remain=remain_ex,
                n=carto_n,
            )
            self._paint_hold_line(
                self._carto_fc,
                prefix=t("for_sale_carto_fc"),
                empty=False,
                base_cr=int(snap.get("carto_fc_cr") or 0),
                fl_cr=int(snap.get("carto_fc_first_cr") or 0),
                remain=remain_ex,
            )
        n = int(snap.get("bio_n") if snap.get("bio_n") is not None else snap.get("n") or 0)
        cr = int(snap.get("bio_cr") if snap.get("bio_cr") is not None else snap.get("cr") or 0)
        bio_fl = int(snap.get("bio_first_cr") or 0)
        remain_bio = self.rail.snap.get("remain")
        if n <= 0:
            self._paint_hold_line(self._bio_hold, prefix=t("for_sale_bio"), empty=True)
            self._paint_hold_line(self._bio_fc, prefix=t("for_sale_bio_fc"), empty=True, hide=True)
        else:
            self._paint_hold_line(
                self._bio_hold,
                prefix=t("for_sale_bio"),
                empty=False,
                base_cr=cr,
                fl_cr=bio_fl,
                remain=remain_bio,
                n=n,
            )
            self._paint_hold_line(
                self._bio_fc,
                prefix=t("for_sale_bio_fc"),
                empty=False,
                base_cr=int(snap.get("bio_fc_cr") or 0),
                fl_cr=int(snap.get("bio_fc_first_cr") or 0),
                remain=remain_bio,
            )

    def _on_right_configure(self, event) -> None:
        inner = max(event.width - 24, 160)
        self.verdict_lbl.config(wraplength=inner)
        self.verdict_sub.config(wraplength=inner)
        self.body_lbl.config(wraplength=max(inner - 40, 120))
        self.meta_lbl.config(wraplength=inner)

    def _on_list_configure(self, _e=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all") or (0, 0, 0, 0))
        first, last = self.canvas.yview()
        self._on_yview(first, last)

    def _on_canvas_width(self, event) -> None:
        self.canvas.itemconfigure(self._win, width=max(event.width, 1))
        first, last = self.canvas.yview()
        self._on_yview(first, last)

    def _pointer_in(self, widget, event) -> bool:
        found = self.root.winfo_containing(event.x_root, event.y_root)
        while found is not None:
            if found == widget:
                return True
            found = getattr(found, "master", None)
        return False

    def _wheel(self, steps: int) -> None:
        if not self._scroll_needed():
            return
        self.canvas.yview_scroll(steps, "units")

    def _on_wheel(self, event) -> None:
        if self._eddn_wheel(-1 if event.delta > 0 else 1, event):
            return
        if self._pointer_in(self._macro_col, event):
            self._macro_pane.wheel(-1 if event.delta > 0 else 1)
            return
        if self._pointer_in(self._left_pane.wrap, event):
            self._left_pane.wheel(-1 if event.delta > 0 else 1)
        elif self._pointer_in(self.canvas, event) or self._pointer_in(self._scroll, event):
            self._wheel(-1 if event.delta > 0 else 1)

    def _on_button_wheel(self, event, steps: int) -> None:
        if self._eddn_wheel(steps, event):
            return
        if self._pointer_in(self._macro_col, event):
            self._macro_pane.wheel(steps)
            return
        if self._pointer_in(self._left_pane.wrap, event):
            self._left_pane.wheel(steps)
        elif self._pointer_in(self.canvas, event) or self._pointer_in(self._scroll, event):
            self._wheel(steps)

    def _eddn_wheel(self, steps: int, event) -> bool:
        overlay = getattr(self, "_eddn_overlay", None)
        box = getattr(self, "_eddn_box", None)
        if overlay is None or box is None or not overlay.winfo_exists():
            return False
        if not self._pointer_in(overlay, event):
            return False
        box.yview_scroll(steps, "units")
        return True

    def _scroll_needed(self) -> bool:
        bbox = self.canvas.bbox("all")
        if not bbox:
            return False
        view = max(self.canvas.winfo_height(), 1)
        return (bbox[3] - bbox[1]) > view + 12

    def _set_drag(self, value: float | None) -> None:
        self._drag_off = value

    def _on_yview(self, first, last) -> None:
        self._first, self._last = float(first), float(last)
        self._draw_scroll(self._scroll_hover)

    def _thumb_geom(self) -> tuple[float, float, float, float, float]:
        h = max(self._scroll.winfo_height(), 1)
        pad = 8.0
        track = max(h - 2 * pad, 1.0)
        span = min(max(self._last - self._first, 0.08), 1.0)
        thumb_h = max(24.0, min(track * span, track * 0.85))
        travel = max(track - thumb_h, 1.0)
        t = self._first / max(1.0 - (self._last - self._first), 1e-6)
        t = max(0.0, min(1.0, t))
        return pad, track, thumb_h, pad + t * travel, span

    def _draw_scroll(self, hover: bool = False) -> None:
        self._scroll_hover = hover
        if not self._scroll_needed():
            if self._scroll.winfo_ismapped():
                self._scroll.pack_forget()
            self._scroll.delete("all")
            return
        if not self._scroll.winfo_ismapped():
            self._scroll.pack(side="right", fill="y", before=self.rail, padx=(0, 1))
            return
        self._scroll.delete("all")
        h = max(self._scroll.winfo_height(), 1)
        pad, _track, thumb_h, thumb_y, _span = self._thumb_geom()
        mid = SCROLL_W / 2
        self._scroll.create_line(mid, pad, mid, h - pad, fill=CYAN_DEEP, width=1)
        fill = CYAN if hover or self._drag_off is not None else CYAN_DIM
        x0, x1 = mid - 2, mid + 2
        self._scroll.create_rectangle(
            x0, thumb_y, x1, thumb_y + thumb_h,
            fill=fill, outline="",
        )

    def _scroll_down(self, event) -> None:
        _pad, _track, thumb_h, thumb_y, _span = self._thumb_geom()
        if thumb_y <= event.y <= thumb_y + thumb_h:
            self._drag_off = event.y - thumb_y
        else:
            self._drag_off = thumb_h / 2
            self._scroll_to_y(event.y)
        self._draw_scroll(hover=True)

    def _scroll_drag(self, event) -> None:
        if self._drag_off is None:
            self._drag_off = 0
        self._scroll_to_y(event.y)

    def _scroll_to_y(self, y: float) -> None:
        pad, track, thumb_h, _ty, span = self._thumb_geom()
        travel = max(track - thumb_h, 1.0)
        t = (y - pad - (self._drag_off or 0)) / travel
        first = max(0.0, min(1.0, t)) * max(1.0 - span, 0.0)
        self.canvas.yview_moveto(first)

    def _start_watcher(self, journal_dir: str | None) -> None:
        def worker() -> None:
            try:
                session, watcher, path, current, offset = prepare_live(
                    journal_dir, live_display=False, on_update=self.q.put,
                )
                xlsx = str(session.wb.path) if session.wb else None
                self.q.put({"_meta": True, "status": f"Journal : {path}", "xlsx": xlsx})
                follow_live(session, watcher, path, current, offset)
            except Exception as exc:
                self.q.put({"_error": str(exc)})

        threading.Thread(target=worker, daemon=True).start()

    def _start_update_check(self) -> None:
        def worker() -> None:
            try:
                tag = newer_release()
            except Exception:
                return
            if tag:
                self.root.after(0, lambda: self._show_update(tag))

        threading.Thread(target=worker, daemon=True).start()

    def _show_update(self, tag: str) -> None:
        self._upd_lbl.config(text=t("update_available", tag=tag))

    def _drain(self) -> None:
        try:
            while True:
                item = self.q.get_nowait()
                if isinstance(item, dict) and item.get("_error"):
                    self.status_lbl.config(text=item["_error"], fg=TIER_BAR["low"])
                elif isinstance(item, dict) and item.get("_meta"):
                    if "status" in item:
                        self.status_lbl.config(text=item["status"])
                    if "xlsx" in item:
                        self.workbook_path = Path(item["xlsx"])
                elif isinstance(item, dict) and item.get("_rank"):
                    self.rail.set_snap(item)
                    if self._hold_snap:
                        self._render_hold(self._hold_snap)
                elif isinstance(item, dict) and item.get("_explore_rank"):
                    self.explore_rail.set_snap(item)
                    if self._hold_snap:
                        self._render_hold(self._hold_snap)
                elif isinstance(item, dict) and item.get("_hold"):
                    self._hold_snap = item
                    self._render_hold(item)
                elif isinstance(item, dict) and (
                    "system" in item or item.get("system_bodies") is not None
                ):
                    self._apply(item)
                    self.status_lbl.config(text=t("live"))
        except queue.Empty:
            pass
        self.root.after(200, self._drain)

    def _default_id(self):
        rows = self._sys.get("system_bodies") or []
        for row in rows:
            if not row.get("done"):
                return row.get("body_id")
        return rows[0].get("body_id") if rows else None

    def _apply(self, item: dict) -> None:
        sys_name = item.get("system") or ""
        if sys_name and sys_name != self._sys_name:
            self._details.clear()
            self._selected_id = None
            self._list_sig = None
            self._sys_name = sys_name
        if item.get("system_bodies") is not None:
            self._sys = item
            for row in item["system_bodies"]:
                det = row.get("detail")
                bid = row.get("body_id")
                if det is not None and bid is not None:
                    self._details[bid] = det
        if item.get("body") and not item.get("_system"):
            bid = item.get("body_id")
            if bid is not None:
                self._details[bid] = item
        if item.get("select"):
            bid = item.get("body_id")
            if bid is None:
                bid = item.get("selected_id")
            if bid is not None:
                self._selected_id = bid
        if self._selected_id is None:
            self._selected_id = self._default_id()
        self._render_list()
        det = self._details.get(self._selected_id)
        if det:
            self._render_detail(det)
        else:
            self._render_detail({
                "system": self._sys.get("system") or "",
                "body": "",
                "pre_dss": True,
                "todo": [],
                "ongoing": [],
                "done_rows": [],
            })

    def _select(self, body_id) -> None:
        if body_id == self._selected_id:
            return
        self._selected_id = body_id
        self._list_sig = None
        self._render_list()
        det = self._details.get(body_id)
        if det:
            self._render_detail(det)

    def _bind_click(self, widget, handler) -> None:
        widget.bind("<Button-1>", handler)
        for child in widget.winfo_children():
            self._bind_click(child, handler)

    def _render_list(self) -> None:
        rows = self._sys.get("system_bodies") or []
        sig_parts = [
            str(self._selected_id),
            self._sys.get("sys_value") or "",
            self._sys.get("sys_empty") or "",
            str(self._sys.get("nsp_count") or 0),
            self._sys.get("nsp_label") or "",
        ]
        for row in rows:
            sig_parts.append(
                f"{row.get('body_id')}|{row.get('value')}|{row.get('status')}|"
                f"{row.get('tier')}|{row.get('bios')}|{row.get('kind')}|"
                f"{row.get('line2')}|{row.get('fss_color')}|{row.get('prior')}"
            )
        sig = "|".join(sig_parts)
        if sig == self._list_sig:
            return
        self._list_sig = sig
        for child in self._left_list.winfo_children():
            child.destroy()
        self.sys_lbl.config(text=self._sys.get("system") or "SCANDECK")
        self.sys_meta.config(text=self._sys.get("sys_value") or "")
        nsp = int(self._sys.get("nsp_count") or 0)
        if nsp:
            tk.Label(
                self._left_list,
                text=self._sys.get("nsp_label") or "",
                fg=CYAN_HI, bg=CYAN_DEEP,
                font=_font(9, "bold"),
                justify="left", anchor="w",
                wraplength=240, padx=10, pady=8,
            ).pack(fill="x", padx=4, pady=(4, 8))
        if not rows:
            tk.Label(
                self._left_list,
                text=self._sys.get("sys_empty") or t("honk_empty"),
                fg=MUTED, bg=BG, font=_font(9), justify="left", anchor="w",
            ).pack(anchor="w", padx=4, pady=12)
        else:
            for row in rows:
                self._list_row(row)
        self.root.after_idle(self._left_pane._on_inner)
        self.root.after(40, self._left_pane._on_inner)

    def _list_row(self, row: dict) -> None:
        bid = row.get("body_id")
        selected = bid == self._selected_id
        bg = CARD2 if selected else BG
        wrap = tk.Frame(self._left_list, bg=CYAN if selected else BG, cursor="hand2")
        wrap.pack(fill="x", pady=(0, 4), padx=(4, 4))
        inner = tk.Frame(wrap, bg=bg)
        inner.pack(fill="x", padx=(3 if selected else 0, 0))
        swatch = tk.Frame(inner, bg=row.get("fss_color") or MUTED, width=6)
        swatch.pack(side="left", fill="y")
        swatch.pack_propagate(False)
        texts = tk.Frame(inner, bg=bg)
        texts.pack(side="left", fill="both", expand=True)
        top = tk.Frame(texts, bg=bg)
        top.pack(fill="x", padx=8, pady=(6, 0))
        mark = "▶" if selected else " "
        tk.Label(
            top, text=f"{mark}  {row.get('short', '')}",
            fg=TEXT, bg=bg, font=_font(10, "bold" if selected else "normal"),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        tk.Label(
            top, text=row.get("icon") or "",
            fg=TIER_BAR.get(row.get("tier"), MUTED), bg=bg, font=_font(10),
            anchor="e",
        ).pack(side="right")
        bot = tk.Frame(texts, bg=bg)
        bot.pack(fill="x", padx=8, pady=(0, 6))
        status = row.get("status") or ""
        if status == "✓":
            st_fg = TIER_BAR["good"]
        elif status == "DSS":
            st_fg = CYAN
        elif status == "skip":
            st_fg = TIER_BAR["low"]
        elif status == "étoile":
            st_fg = CYAN_DIM
        else:
            st_fg = MUTED
        tk.Label(
            bot, text=status, fg=st_fg, bg=bg, font=_font(8, "bold"), anchor="e",
        ).pack(side="right")
        prior = row.get("prior") or ""
        if prior:
            tk.Label(
                bot, text=prior, fg=CYAN_DIM, bg=bg, font=_font(8), anchor="e",
            ).pack(side="right", padx=(0, 8))
        tk.Label(
            bot, text=row.get("line2") or "",
            fg=TIER_BAR.get(row.get("map_tier"), MUTED) if (
                row.get("map_label") and not row.get("bios")
            ) else MUTED,
            bg=bg, font=_font(8), anchor="w",
        ).pack(side="left", fill="x", expand=True)
        self._bind_click(wrap, lambda _e, body_id=bid: self._select(body_id))

    def _render_detail(self, snap: dict) -> None:
        self._snap = snap
        self.sys_lbl.config(text=self._sys.get("system") or snap.get("system") or "SCANDECK")
        has_body = bool(snap.get("body"))
        self.body_lbl.config(
            text=snap.get("body") or t("waiting_dss"),
            fg=TEXT if has_body else MUTED,
        )
        bits = [snap.get("summary") or ""]
        if snap.get("gravity") is not None:
            bits.append(f"{snap['gravity']} G")
        if has_body and snap.get("kind") != "star":
            bits.append(t("volcanism", value=snap.get("volcanism") or t("none")))
        if snap.get("dss"):
            bits.append(t("dss", names=", ".join(snap["dss"])))
        self.meta_lbl.config(text="  ·  ".join(b for b in bits if b))
        total = snap.get("total") or 0
        if has_body and total and snap.get("kind") != "star":
            self.scan_lbl.config(text=t("scans", done=snap.get("done", 0), total=total))
        elif has_body:
            self.scan_lbl.config(text="")
        else:
            self.scan_lbl.config(text="")
            self.meta_lbl.config(text="")
        tone = snap.get("verdict_tone") or "ok"
        raw = snap.get("verdict") or ""
        if "  ·  " in raw:
            title, detail = raw.split("  ·  ", 1)
        else:
            title, detail = raw, ""
        self.verdict_lbl.config(text=title, fg=TIER_BAR.get(tone, CYAN))
        self.verdict_sub.config(text=detail)

        if snap.get("alert"):
            self.alert_lbl.config(text=t("alert_land"))
            if not self.alert_lbl.winfo_ismapped():
                self.alert_lbl.pack(fill="x", padx=18, pady=(0, 6), before=self.verdict_lbl)
        elif self.alert_lbl.winfo_ismapped():
            self.alert_lbl.pack_forget()

        for child in self.list_fr.winfo_children():
            child.destroy()

        sections = (
            (t("section_ongoing"), snap.get("ongoing") or []),
            (t("section_todo"), snap.get("todo") or []),
            (t("section_done"), snap.get("done_rows") or []),
        )
        if not any(rows for _, rows in sections):
            if not has_body:
                empty = self._sys.get("sys_empty") or t("empty_click")
            elif snap.get("pre_dss"):
                empty = t("empty_dss")
            else:
                empty = t("empty_species")
            tk.Label(
                self.list_fr, text=empty,
                fg=MUTED, bg=BG, font=_font(10),
            ).pack(anchor="w", padx=6, pady=12)
            self.root.after(10, self._on_list_configure)
            return
        for title, rows in sections:
            if not rows:
                continue
            tk.Label(
                self.list_fr, text=title, fg=CYAN_DIM, bg=BG,
                font=_font(8, "bold"),
            ).pack(anchor="w", padx=6, pady=(10, 2))
            for row in rows:
                self._card(row)
        self.root.after(10, self._on_list_configure)

    def _card(self, row: dict) -> None:
        compact = row.get("tier") in {"low", "ok"}
        tiny = row.get("tier") == "low"
        accent = TIER_BAR.get(row.get("tier"), MUTED)
        wrap = tk.Frame(self.list_fr, bg=LINE)
        wrap.pack(fill="x", padx=6, pady=2 if tiny else 5)
        inner = tk.Frame(wrap, bg=CARD)
        inner.pack(fill="x", padx=1, pady=1)
        bar = tk.Frame(inner, bg=accent, width=4 if tiny else 6)
        bar.pack(side="left", fill="y")
        bar.pack_propagate(False)
        pad = 5 if compact else 9
        body = tk.Frame(inner, bg=CARD)
        body.pack(side="left", fill="x", expand=True, padx=10, pady=pad)
        hard = t("hard_see") if row.get("hard") else ""
        name_size = 9 if tiny else (11 if compact else 12)
        name_fg = MUTED if tiny else TEXT
        icon = row.get("icon") or ""
        tk.Label(
            body, text=f"{icon}  {row.get('name', '')}".strip(),
            fg=name_fg, bg=CARD, font=_font(name_size, "bold" if not tiny else "normal"),
            anchor="w",
        ).pack(fill="x")
        dist = f"   ·   {row['dist']} m" if row.get("dist") else ""
        price_size = 9 if tiny else (11 if compact else 13)
        tk.Label(
            body,
            text=f"{row.get('value', '')}  →  {row.get('first', '')} First Logged{dist}",
            fg=accent, bg=CARD, font=_font(price_size, "bold" if not tiny else "normal"),
            anchor="w",
        ).pack(fill="x", pady=(1 if tiny else 2, 0))
        tk.Label(
            body, text=f"{row.get('status', '')}{hard}",
            fg=MUTED, bg=CARD, font=_font(8 if tiny else 10), anchor="w",
        ).pack(fill="x")
        if row.get("alts"):
            tk.Label(
                body, text=row["alts"],
                fg=MUTED, bg=CARD, font=_font(8), anchor="w",
            ).pack(fill="x")

    def _send_inara(self) -> None:
        self.status_lbl.config(text=t("inara_sending"), fg=MUTED)

        def worker() -> None:
            result = inara_sync()
            self.root.after(0, lambda: self._inara_done(result))

        threading.Thread(target=worker, daemon=True).start()

    def _inara_done(self, result: dict) -> None:
        detail = result.get("detail")
        if result.get("ok"):
            self.status_lbl.config(text=t("inara_ok"), fg=READY)
        elif detail == "missing_key":
            self.status_lbl.config(text=t("inara_need_key"), fg=TIER_BAR["low"])
        elif detail == "no_cmdr":
            self.status_lbl.config(text=t("inara_need_cmdr"), fg=TIER_BAR["low"])
        elif detail == "nothing":
            self.status_lbl.config(text=t("inara_nothing"), fg=TIER_BAR["low"])
        elif detail == "app_blocked":
            self.status_lbl.config(text=t("inara_app_blocked"), fg=TIER_BAR["low"])
        elif detail == "bad_key":
            self.status_lbl.config(text=t("inara_bad_key"), fg=TIER_BAR["low"])
        elif detail == "blocked_html":
            self.status_lbl.config(text=t("inara_blocked"), fg=TIER_BAR["low"])
        elif detail == "network":
            self.status_lbl.config(text=t("inara_network"), fg=TIER_BAR["low"])
        elif result.get("reason"):
            self.status_lbl.config(
                text=t("inara_fail_detail", reason=str(result["reason"])[:80]),
                fg=TIER_BAR["low"],
            )
        else:
            self.status_lbl.config(text=t("inara_fail"), fg=TIER_BAR["low"])

    def _open_eddn_log(self) -> None:
        existing = getattr(self, "_eddn_overlay", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return
        shade = tk.Frame(self.root, bg=BG)
        shade.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._eddn_overlay = shade
        self._eddn_log_fp = None
        self._pause_hotkeys()
        border = tk.Frame(shade, bg=CYAN)
        border.place(relx=0.5, rely=0.5, anchor="center")
        pad = tk.Frame(border, bg=BG, width=640, height=420)
        pad.pack(padx=1, pady=1)
        pad.pack_propagate(False)
        head = tk.Frame(pad, bg=BG)
        head.pack(fill="x", padx=14, pady=(12, 6))
        self._eddn_title = tk.Label(
            head, text=t("eddn_log_title"), fg=CYAN, bg=BG,
            font=_font(11, "bold"), anchor="w",
        )
        self._eddn_title.pack(side="left", fill="x", expand=True)
        body = tk.Frame(pad, bg=CARD)
        body.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        box = tk.Text(
            body, bg=CARD, fg=TEXT, insertbackground=CYAN, bd=0,
            highlightthickness=0, font=_font(8), wrap="none",
            cursor="xterm", undo=False, takefocus=True,
        )
        scroll = tk.Scrollbar(
            body, orient="vertical", command=box.yview,
            bg=BG, troughcolor=CARD, activebackground=CYAN,
            highlightthickness=0, bd=0, width=10,
        )
        box.configure(yscrollcommand=scroll.set)
        box.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._eddn_box = box
        box.tag_config("ok", foreground=READY)
        box.tag_config("rejected", foreground=WARN)
        box.tag_config("error", foreground=TIER_BAR["low"])
        box.tag_config("muted", foreground=MUTED)
        box.tag_config("sel", background=CYAN_DEEP, foreground=CYAN_HI)
        hint = tk.Label(pad, text="", fg=MUTED, bg=BG, font=_font(8), anchor="w")
        hint.pack(fill="x", padx=14, pady=(0, 4))
        btns = tk.Frame(pad, bg=BG)
        btns.pack(fill="x", padx=14, pady=(0, 12))

        def close(_e=None) -> None:
            aid = getattr(self, "_eddn_after", None)
            if aid is not None:
                try:
                    self.root.after_cancel(aid)
                except tk.TclError:
                    pass
            self._eddn_after = None
            self.root.unbind("<Escape>")
            shade.destroy()
            self._eddn_overlay = None
            self._eddn_box = None
            self._resume_hotkeys()

        def _selected() -> str:
            try:
                return box.get("sel.first", "sel.last")
            except tk.TclError:
                return ""

        def _copy_text(text: str, ok_key: str) -> None:
            text = text.strip()
            if not text:
                hint.config(text=t("nothing_to_copy"), fg=TIER_BAR["low"])
                return
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update_idletasks()
            preview = text.splitlines()[0]
            if len(preview) > 48:
                preview = preview[:48] + "…"
            extra = f"  ·  {len(text.splitlines())}" if "\n" in text else ""
            hint.config(text=t(ok_key, text=preview) + extra, fg=READY)

        def copy_sel(_e=None):
            chunk = _selected()
            _copy_text(chunk, "copied")
            return "break"

        def copy_all(_e=None):
            _copy_text(box.get("1.0", "end-1c"), "copied")
            return "break"

        def select_all(_e=None):
            box.tag_add("sel", "1.0", "end-1c")
            box.mark_set("insert", "1.0")
            return "break"

        def copy_or_all(_e=None):
            return copy_sel() if _selected() else copy_all()

        def on_key(event):
            ctrl = bool(event.state & 0x4)
            if ctrl and event.keysym.lower() == "c":
                return copy_or_all()
            if ctrl and event.keysym.lower() == "a":
                return select_all()
            if event.keysym in {
                "Up", "Down", "Left", "Right", "Prior", "Next",
                "Home", "End", "Shift_L", "Shift_R", "Control_L", "Control_R",
            }:
                return None
            return "break"

        def refresh() -> None:
            if getattr(self, "_eddn_overlay", None) is None:
                return
            hub = get_hub()
            counts = hub.counts()
            self._eddn_title.config(
                text=t(
                    "eddn_log_counts",
                    ok=counts.get("ok", 0),
                    rejected=counts.get("rejected", 0),
                    error=counts.get("error", 0),
                )
            )
            rows = hub.logs()
            last = rows[-1] if rows else {}
            fp = (
                len(rows),
                last.get("ts"),
                last.get("event"),
                last.get("status"),
                counts.get("ok", 0),
                counts.get("rejected", 0),
                counts.get("error", 0),
            )
            if fp != self._eddn_log_fp:
                self._eddn_log_fp = fp
                view = box.yview()
                try:
                    sel = (box.index("sel.first"), box.index("sel.last"))
                except tk.TclError:
                    sel = None
                box.delete("1.0", "end")
                if not rows:
                    box.insert("end", t("eddn_log_empty") + "\n", "muted")
                for row in reversed(rows):
                    tag = row.get("status") or "muted"
                    code = row.get("code")
                    extra = f"  HTTP {code}" if code else ""
                    line = (
                        f"{row.get('ts','')}  {row.get('status','').upper()}  "
                        f"{row.get('event','')}  {row.get('schema','')}{extra}"
                    )
                    box.insert(
                        "end", line + "\n",
                        tag if tag in {"ok", "rejected", "error"} else "muted",
                    )
                    detail = (row.get("detail") or "").strip()
                    if detail and tag != "ok":
                        box.insert("end", f"    {detail}\n", "muted")
                box.yview_moveto(view[0])
                if sel is not None:
                    try:
                        box.tag_add("sel", sel[0], sel[1])
                    except tk.TclError:
                        pass
            self._eddn_after = self.root.after(1500, refresh)

        box.bind("<Key>", on_key)
        box.bind("<Control-c>", copy_or_all)
        box.bind("<Control-a>", select_all)
        _outline_btn(btns, t("eddn_copy_sel"), copy_sel)
        _outline_btn(btns, t("eddn_copy_all"), copy_all)
        _outline_btn(btns, t("options_cancel"), close)
        self.root.bind("<Escape>", close)
        refresh()
        box.focus_set()

    def _build_macro_col(self) -> None:
        """Liste des macros (le titre MACROS est dans l’en-tête, aligné sur Vista)."""
        inner = tk.Frame(self._macro_col, bg=BG)
        inner.pack(fill="both", expand=True)
        new_row = tk.Frame(inner, bg=BG)
        new_row.pack(fill="x", padx=12, pady=(10, 8))
        _outline_btn(new_row, t("macros_new"), self._macro_new)
        self._macro_hint = tk.Label(
            inner, text=t("macros_hint"), fg=MUTED, bg=BG,
            font=_font(7), anchor="w", justify="left", wraplength=MACRO_COL_W - 28,
        )
        self._macro_hint.pack(fill="x", padx=12, pady=(0, 8))
        self._macro_pane = ThinPane(inner)
        self._macro_pane.wrap.pack(fill="both", expand=True, pady=(0, 8))
        self._macro_list = self._macro_pane.inner
        self._refresh_macros()

    def _refresh_macros(self) -> None:
        for child in self._macro_list.winfo_children():
            child.destroy()
        rows = load_macros()
        if not rows:
            tk.Label(
                self._macro_list, text=t("macros_empty"), fg=MUTED, bg=BG,
                font=_font(8), anchor="w", justify="left", wraplength=MACRO_COL_W - 32,
            ).pack(fill="x", padx=8, pady=8)
            self.root.after(20, self._macro_pane._on_inner)
            self._sync_macro_hotkeys()
            return
        for row in rows:
            self._macro_row(row)
        self.root.after(20, self._macro_pane._on_inner)
        self._sync_macro_hotkeys()

    def _macro_row(self, row: dict) -> None:
        wrap = tk.Frame(self._macro_list, bg=CARD)
        wrap.pack(fill="x", padx=12, pady=(0, 8))
        top = tk.Frame(wrap, bg=CARD)
        top.pack(fill="x", padx=6, pady=(6, 2))
        name = tk.Label(
            top, text=row.get("name") or "?", fg=CYAN, bg=CARD,
            font=_font(9, "bold"), anchor="w", cursor="hand2", wraplength=MACRO_COL_W - 90,
            justify="left",
        )
        name.pack(side="left", fill="x", expand=True)
        name.bind("<Button-1>", lambda _e, m=row: self._macro_play(m))
        wrap.bind("<Button-1>", lambda _e, m=row: self._macro_play(m))
        bind = (row.get("hotkey") or "").strip()
        tk.Label(
            top, text=f"[{pretty_key(bind)}]" if bind else "", fg=CYAN_HI, bg=CARD,
            font=_font(8, "bold"),
        ).pack(side="right")
        btns = tk.Frame(wrap, bg=CARD)
        btns.pack(fill="x", padx=6, pady=(0, 6))
        edit = tk.Label(
            btns, text=t("macros_edit"), fg=MUTED, bg=CARD,
            font=_font(7, "bold"), cursor="hand2",
        )
        edit.pack(side="left")
        edit.bind("<Button-1>", lambda _e, m=row: self._macro_edit(m))
        tk.Label(btns, text=" · ", fg=LINE, bg=CARD, font=_font(7)).pack(side="left")
        delete = tk.Label(
            btns, text=t("macros_delete"), fg=MUTED, bg=CARD,
            font=_font(7, "bold"), cursor="hand2",
        )
        delete.pack(side="left")
        delete.bind("<Button-1>", lambda _e, m=row: self._macro_delete(m))

    def _on_close(self) -> None:
        grabber = getattr(self, "_hotkeys", None)
        if grabber is not None:
            grabber.stop()
        self.root.destroy()

    def _sync_macro_hotkeys(self) -> None:
        grabber = getattr(self, "_hotkeys", None)
        if grabber is not None:
            grabber.set_macros(binds_map())

    def _pause_hotkeys(self) -> None:
        """Coupe l’écoute pendant l’éditeur / Options, sinon la touche lance la macro."""
        grabber = getattr(self, "_hotkeys", None)
        if grabber is not None:
            grabber.pause()

    def _resume_hotkeys(self) -> None:
        grabber = getattr(self, "_hotkeys", None)
        if grabber is not None:
            grabber.resume()
            grabber.set_macros(binds_map())

    def _macro_play(self, row: dict) -> None:
        """Clic sur le nom ou touche de lancement → envoi vers Elite."""
        if is_playing():
            self.status_lbl.config(text=t("macros_busy"), fg=TIER_BAR["low"])
            return
        self.status_lbl.config(text=t("macros_playing", name=row.get("name") or ""), fg=MUTED)
        self._pause_hotkeys()

        def done(err: str | None) -> None:
            def apply() -> None:
                self._resume_hotkeys()
                if err == "need_xdotool":
                    self.status_lbl.config(text=t("macros_need_xdotool"), fg=TIER_BAR["low"])
                elif err == "no_window":
                    self.status_lbl.config(text=t("macros_no_window"), fg=TIER_BAR["low"])
                elif err == "empty":
                    self.status_lbl.config(text=t("macros_empty_play"), fg=TIER_BAR["low"])
                elif err:
                    self.status_lbl.config(text=t("macros_fail"), fg=TIER_BAR["low"])
                else:
                    self.status_lbl.config(text=t("macros_done", name=row.get("name") or ""), fg=READY)
            self.root.after(0, apply)

        err = play_macro(row, on_done=done)
        if err == "busy":
            self._resume_hotkeys()
            self.status_lbl.config(text=t("macros_busy"), fg=TIER_BAR["low"])
        elif err == "empty":
            self._resume_hotkeys()
            self.status_lbl.config(text=t("macros_empty_play"), fg=TIER_BAR["low"])

    def _macro_delete(self, row: dict) -> None:
        delete_macro(str(row.get("id") or ""))
        self._refresh_macros()

    def _macro_new(self) -> None:
        self._macro_editor(None)

    def _macro_edit(self, row: dict) -> None:
        self._macro_editor(row)

    def _macro_editor(self, existing: dict | None) -> None:
        """Overlay : nom, touche de lancement, enregistrement type VoiceAttack (pas un champ texte)."""
        prev = getattr(self, "_macro_overlay", None)
        if prev is not None and prev.winfo_exists():
            prev.lift()
            return
        shade = tk.Frame(self.root, bg=BG)
        shade.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._macro_overlay = shade
        self._pause_hotkeys()
        border = tk.Frame(shade, bg=CYAN)
        border.place(relx=0.5, rely=0.5, anchor="center")
        pad = tk.Frame(border, bg=BG, width=560, height=560)
        pad.pack(padx=1, pady=1)
        pad.pack_propagate(False)
        tk.Label(
            pad, text=t("macros_editor"), fg=CYAN, bg=BG,
            font=_font(11, "bold"), anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(
            pad, text=t("macros_name"), fg=MUTED, bg=BG, font=_font(8), anchor="w",
        ).pack(fill="x", padx=16)
        name_var = tk.StringVar(value=(existing or {}).get("name") or "")
        pad.configure(takefocus=True)
        try:
            shade.grab_set()
        except tk.TclError:
            pass
        name_ent = tk.Entry(
            pad, textvariable=name_var, bg=CARD, fg=TEXT, insertbackground=CYAN,
            highlightbackground=CYAN_DIM, highlightcolor=CYAN, highlightthickness=1,
            bd=0, font=_font(10), disabledforeground=TEXT, readonlybackground=CARD,
        )
        name_ent.pack(fill="x", padx=16, pady=(4, 8), ipady=4)
        tk.Label(
            pad, text=t("macros_hotkey"), fg=MUTED, bg=BG, font=_font(8), anchor="w",
        ).pack(fill="x", padx=16)
        hot_state = {"key": (existing or {}).get("hotkey") or "", "listen": False}
        hot_btn = tk.Label(
            pad, text="", fg=CYAN, bg=CARD, font=_font(10, "bold"),
            cursor="hand2", pady=6, padx=8, anchor="w", takefocus=True,
        )
        hot_btn.pack(fill="x", padx=16, pady=(4, 8))
        rec_lbl = tk.Label(
            pad, text=t("macros_rec_idle"), fg=MUTED, bg=BG,
            font=_font(8), anchor="w", justify="left", wraplength=520,
        )
        rec_lbl.pack(fill="x", padx=16, pady=(0, 6))
        # Boutons en bas d’abord : la zone d’enregistrement (expand) ne doit pas les écraser.
        hint = tk.Label(pad, text="", fg=TIER_BAR["low"], bg=BG, font=_font(8), anchor="w")
        btns = tk.Frame(pad, bg=BG)
        btns.pack(side="bottom", fill="x", padx=16, pady=(12, 18))
        hint.pack(side="bottom", fill="x", padx=16, pady=(0, 4))
        seq_wrap = tk.Frame(pad, bg=CARD)
        seq_wrap.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        seq_canvas = tk.Canvas(seq_wrap, bg=CARD, highlightthickness=0, bd=0, takefocus=False)
        seq_bar = tk.Scrollbar(
            seq_wrap, orient="vertical", command=seq_canvas.yview, width=10,
            bg=BG, troughcolor=CARD, highlightthickness=0, bd=0,
        )
        seq_inner = tk.Frame(seq_canvas, bg=CARD)
        seq_win = seq_canvas.create_window((0, 0), window=seq_inner, anchor="nw")
        seq_canvas.configure(yscrollcommand=seq_bar.set)
        seq_canvas.pack(side="left", fill="both", expand=True)
        seq_bar.pack(side="right", fill="y")
        seq_inner.bind(
            "<Configure>",
            lambda _e: seq_canvas.configure(scrollregion=seq_canvas.bbox("all") or (0, 0, 0, 0)),
        )
        seq_canvas.bind(
            "<Configure>",
            lambda e: seq_canvas.itemconfigure(seq_win, width=max(e.width, 1)),
        )
        state = {
            "recording": False,
            "steps": list((existing or {}).get("steps") or []),
            "down": {},
            "last_up": None,
            "tick": None,
            "pending_up": {},
        }
        live_labels: dict[str, tk.Label] = {}
        skip = {
            "Shift_L", "Shift_R", "Control_L", "Control_R",
            "Alt_L", "Alt_R", "Super_L", "Super_R", "Caps_Lock", "Num_Lock",
        }
        capture_widgets = (shade, pad, hot_btn, seq_canvas, seq_inner)

        def lock_name(lock: bool) -> None:
            name_ent.config(state="readonly" if lock else "normal")
            if lock:
                pad.focus_set()

        def capturing() -> bool:
            return bool(hot_state["listen"] or state["recording"])

        def show_hot() -> None:
            key = hot_state["key"]
            if hot_state["listen"]:
                hot_btn.config(text=t("macros_hotkey_listen"), fg=READY)
            elif key:
                hot_btn.config(text=t("macros_hotkey_set", key=pretty_key(key)), fg=CYAN)
            else:
                hot_btn.config(text=t("macros_hotkey_none"), fg=MUTED)

        def clear_seq() -> None:
            for child in seq_inner.winfo_children():
                child.destroy()

        def add_plus() -> None:
            tk.Label(
                seq_inner, text="+", fg=CYAN, bg=CARD, font=_font(11, "bold"),
            ).pack(anchor="w", padx=12, pady=(4, 2))

        def add_key_block(key: str, hold_ms: int | None, *, live: bool = False) -> tk.Label | None:
            block = tk.Frame(seq_inner, bg=CARD)
            block.pack(anchor="w", padx=12, pady=(0, 2))
            tk.Label(
                block, text=pretty_key(key), fg=CYAN_HI, bg=CARD,
                font=_font(14, "bold"), anchor="w",
            ).pack(anchor="w")
            show_hold = live or (hold_ms is not None and hold_ms > HOLD_TAP_MS)
            if not show_hold:
                return None
            text = format_hold_s(hold_ms or 0) if (hold_ms or 0) > HOLD_TAP_MS else ""
            hold_lbl = tk.Label(
                block, text=text, fg=MUTED, bg=CARD,
                font=_font(8), anchor="w",
            )
            hold_lbl.pack(anchor="w")
            return hold_lbl

        def show_steps() -> None:
            live_labels.clear()
            clear_seq()
            keys = [s for s in state["steps"] if s.get("key")]
            live = list(state["down"].items())
            if not keys and not live:
                tk.Label(
                    seq_inner, text=t("macros_no_steps"), fg=MUTED, bg=CARD,
                    font=_font(8), anchor="w", justify="left",
                ).pack(anchor="w", padx=12, pady=10)
                return
            first = True
            for step in keys:
                if not first:
                    add_plus()
                first = False
                add_key_block(str(step.get("key")), int(step.get("hold_ms") or 0))
            now = time.monotonic()
            for key, t0 in live:
                if not first:
                    add_plus()
                first = False
                hold_lbl = add_key_block(key, int((now - t0) * 1000), live=True)
                if hold_lbl is not None:
                    live_labels[key] = hold_lbl
            seq_canvas.yview_moveto(1.0)

        def stop_tick() -> None:
            aid = state.get("tick")
            if aid is not None:
                try:
                    pad.after_cancel(aid)
                except tk.TclError:
                    pass
                state["tick"] = None

        def tick_live() -> None:
            state["tick"] = None
            if not (state["recording"] and state["down"]):
                return
            now = time.monotonic()
            for key, t0 in state["down"].items():
                lbl = live_labels.get(key)
                if lbl is None:
                    continue
                ms = int((now - t0) * 1000)
                lbl.config(text=format_hold_s(ms) if ms > HOLD_TAP_MS else "")
            state["tick"] = pad.after(80, tick_live)

        def flush_pending_ups() -> None:
            for aid in list(state["pending_up"].values()):
                try:
                    pad.after_cancel(aid)
                except tk.TclError:
                    pass
            state["pending_up"].clear()

        def unbind_capture() -> None:
            self.root.unbind_all("<KeyPress>")
            self.root.unbind_all("<KeyRelease>")
            for w in capture_widgets:
                w.unbind("<KeyPress>")
                w.unbind("<KeyRelease>")

        def bind_capture(press, release=None) -> None:
            unbind_capture()
            self.root.bind_all("<KeyPress>", press)
            self.root.bind_all("<KeyRelease>", release or (lambda _e: "break"))
            for w in capture_widgets:
                w.bind("<KeyPress>", press)
                w.bind("<KeyRelease>", release or (lambda _e: "break"))

        def commit_key(key: str, t_up: float) -> None:
            t0 = state["down"].pop(key, None)
            if t0 is None:
                return
            hold = int((t_up - t0) * 1000)
            state["steps"].append({"key": key, "hold_ms": max(hold, 40)})
            state["last_up"] = t_up
            if not state["down"]:
                stop_tick()
            show_steps()

        def stop_rec() -> None:
            if not state["recording"]:
                return
            stop_tick()
            flush_pending_ups()
            state["recording"] = False
            now = time.monotonic()
            for key, t0 in list(state["down"].items()):
                hold = int((now - t0) * 1000)
                state["steps"].append({"key": key, "hold_ms": max(hold, 40)})
            state["down"].clear()
            unbind_capture()
            rec_lbl.config(text=t("macros_rec_idle"), fg=MUTED)
            lock_name(False)
            show_steps()

        def on_hot_press(event) -> str:
            if not hot_state["listen"]:
                return "break"
            if event.keysym in skip or event.keysym == "Escape":
                if event.keysym == "Escape":
                    hot_state["listen"] = False
                    unbind_capture()
                    lock_name(False)
                    show_hot()
                return "break"
            except_id = (existing or {}).get("id")
            if hotkey_in_use(event.keysym, except_id=except_id):
                hint.config(text=t("macros_hotkey_taken", key=pretty_key(event.keysym)))
                return "break"
            hot_state["key"] = event.keysym
            hot_state["listen"] = False
            unbind_capture()
            lock_name(False)
            hint.config(text="")
            show_hot()
            return "break"

        def start_hot(_e=None) -> None:
            if state["recording"]:
                return
            hot_state["listen"] = True
            hint.config(text="")
            lock_name(True)
            hot_btn.focus_set()
            try:
                hot_btn.focus_force()
            except tk.TclError:
                pad.focus_set()
            show_hot()
            bind_capture(on_hot_press)

        def on_press(event) -> str:
            if event.keysym == "Escape":
                stop_rec()
                return "break"
            if event.keysym in skip:
                return "break"
            aid = state["pending_up"].pop(event.keysym, None)
            if aid is not None:
                try:
                    pad.after_cancel(aid)
                except tk.TclError:
                    pass
                return "break"
            if event.keysym in state["down"]:
                return "break"
            now = time.monotonic()
            state["down"][event.keysym] = now
            show_steps()
            if state["tick"] is None:
                tick_live()
            return "break"

        def on_release(event) -> str:
            key = event.keysym
            if key not in state["down"] or key in state["pending_up"]:
                return "break"
            t_up = time.monotonic()

            def confirm(k=key, when=t_up) -> None:
                state["pending_up"].pop(k, None)
                commit_key(k, when)

            state["pending_up"][key] = pad.after(40, confirm)
            return "break"

        def start_rec() -> None:
            hot_state["listen"] = False
            state["recording"] = True
            flush_pending_ups()
            state["steps"] = []
            state["down"] = {}
            state["last_up"] = None
            rec_lbl.config(text=t("macros_rec_live"), fg=READY)
            lock_name(True)
            pad.focus_set()
            show_steps()
            bind_capture(on_press, on_release)

        def close(_e=None) -> None:
            stop_rec()
            hot_state["listen"] = False
            unbind_capture()
            self.root.unbind("<Escape>")
            try:
                shade.grab_release()
            except tk.TclError:
                pass
            shade.destroy()
            self._macro_overlay = None
            self._resume_hotkeys()

        def on_escape(_e=None):
            if hot_state["listen"]:
                hot_state["listen"] = False
                unbind_capture()
                lock_name(False)
                show_hot()
                return "break"
            if state["recording"]:
                stop_rec()
                return "break"
            close()

        def save() -> None:
            stop_rec()
            name = name_var.get().strip()
            if not name:
                hint.config(text=t("macros_need_name"))
                return
            if not hot_state["key"]:
                hint.config(text=t("macros_need_hotkey"))
                return
            if not state["steps"]:
                hint.config(text=t("macros_need_steps"))
                return
            upsert_macro(
                {
                    "name": name,
                    "hotkey": hot_state["key"],
                    "steps": state["steps"],
                },
                replace_id=(existing or {}).get("id"),
            )
            close()
            self._refresh_macros()

        def on_name_keypress(event):
            if hot_state["listen"]:
                return on_hot_press(event)
            if state["recording"]:
                return on_press(event)
            return None

        def on_name_keyrelease(event):
            if state["recording"]:
                return on_release(event)
            if hot_state["listen"]:
                return "break"
            return None

        def on_name_focus(_e):
            if capturing():
                pad.focus_set()
                return "break"
            return None

        name_ent.bind("<KeyPress>", on_name_keypress)
        name_ent.bind("<KeyRelease>", on_name_keyrelease)
        name_ent.bind("<FocusIn>", on_name_focus)
        hot_btn.bind("<Button-1>", start_hot)
        seq_canvas.bind("<Button-1>", lambda _e: pad.focus_set() if capturing() else None)
        show_hot()
        _outline_btn(btns, t("macros_record"), start_rec, padx=14, pady=7)
        _outline_btn(btns, t("macros_save"), save, padx=14, pady=7)
        _outline_btn(btns, t("options_cancel"), close, padx=14, pady=7)
        self.root.bind("<Escape>", on_escape)
        show_steps()
        pad.focus_set()

    def _open_xlsx(self) -> None:
        if not self.workbook_path or not self.workbook_path.exists():
            self.status_lbl.config(text=t("no_sheet"))
            return
        path = str(self.workbook_path)
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def _open_options(self) -> None:
        existing = getattr(self, "_opt_overlay", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return

        cfg = load_config()
        shade = tk.Frame(self.root, bg=BG)
        shade.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._opt_overlay = shade
        self._pause_hotkeys()

        border = tk.Frame(shade, bg=CYAN)
        border.place(relx=0.5, rely=0.5, anchor="center")
        pad = tk.Frame(border, bg=BG, width=460)
        pad.pack(padx=1, pady=1)
        pad.pack_propagate(True)

        tk.Label(
            pad, text=t("options_title").upper(), fg=CYAN, bg=BG,
            font=_font(11, "bold"), anchor="w",
        ).pack(fill="x", padx=18, pady=(16, 12))

        tk.Label(
            pad, text=t("options_lang").upper(), fg=CYAN, bg=BG,
            font=_font(8, "bold"), anchor="w",
        ).pack(fill="x", padx=18)
        lang_var = tk.StringVar(value="auto" if is_auto() else lang())
        radios = tk.Frame(pad, bg=BG)
        radios.pack(fill="x", padx=18, pady=(6, 16))
        for code, key in (
            ("auto", "lang_auto"),
            ("en", "lang_en"),
            ("fr", "lang_fr"),
            ("es", "lang_es"),
        ):
            tk.Radiobutton(
                radios, text=t(key), variable=lang_var, value=code,
                fg=TEXT, bg=BG, selectcolor=CYAN_DEEP, activebackground=BG,
                activeforeground=CYAN, highlightthickness=0, bd=0,
                font=_font(9), anchor="w", cursor="hand2",
            ).pack(anchor="w")

        tk.Label(
            pad, text=t("options_journals").upper(), fg=CYAN, bg=BG,
            font=_font(8, "bold"), anchor="w",
        ).pack(fill="x", padx=18)
        path_row = tk.Frame(pad, bg=BG)
        path_row.pack(fill="x", padx=18, pady=(6, 4))
        path_var = tk.StringVar(value=cfg.get("journal_dir") or "")
        entry = tk.Entry(
            path_row, textvariable=path_var, bg=CARD, fg=TEXT,
            insertbackground=CYAN, highlightbackground=CYAN_DIM,
            highlightcolor=CYAN, highlightthickness=1, bd=0,
            font=_font(9),
        )
        entry.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 8))

        def browse() -> None:
            start = path_var.get().strip() or str(guessed_journal_dir() or Path.home())
            picked = filedialog.askdirectory(parent=self.root, initialdir=start)
            if picked:
                path_var.set(picked)

        _outline_btn(path_row, t("options_browse"), browse)
        guessed = guessed_journal_dir()
        hint = f"\n({guessed})" if guessed else ""
        tk.Label(
            pad, text=t("options_auto_path", hint=hint), fg=MUTED, bg=BG,
            font=_font(8), anchor="w", justify="left", wraplength=420,
        ).pack(fill="x", padx=18)

        tk.Label(
            pad, text=t("options_share").upper(), fg=CYAN, bg=BG,
            font=_font(8, "bold"), anchor="w",
        ).pack(fill="x", padx=18, pady=(14, 4))
        eddn_var = tk.BooleanVar(value=bool(cfg.get("eddn_enabled", True)))
        tk.Checkbutton(
            pad, text=t("options_eddn"), variable=eddn_var,
            fg=TEXT, bg=BG, selectcolor=CYAN_DEEP, activebackground=BG,
            activeforeground=CYAN, highlightthickness=0, bd=0,
            font=_font(9), anchor="w", cursor="hand2",
        ).pack(fill="x", padx=18)
        tk.Label(
            pad, text=t("options_eddn_hint"), fg=MUTED, bg=BG,
            font=_font(8), anchor="w", justify="left", wraplength=420,
        ).pack(fill="x", padx=18, pady=(0, 8))
        tk.Label(
            pad, text=t("options_inara_key"), fg=MUTED, bg=BG,
            font=_font(8), anchor="w",
        ).pack(fill="x", padx=18)
        inara_var = tk.StringVar(value=cfg.get("inara_api_key") or "")
        inara_entry = tk.Entry(
            pad, textvariable=inara_var, bg=CARD, fg=TEXT, show="*",
            insertbackground=CYAN, highlightbackground=CYAN_DIM,
            highlightcolor=CYAN, highlightthickness=1, bd=0,
            font=_font(9),
        )
        inara_entry.pack(fill="x", padx=18, pady=(4, 0), ipady=4)
        tk.Label(
            pad, text=t("options_inara_hint"), fg=MUTED, bg=BG,
            font=_font(8), anchor="w", justify="left", wraplength=420,
        ).pack(fill="x", padx=18, pady=(4, 0))

        err = tk.Label(pad, text="", fg=TIER_BAR["low"], bg=BG, font=_font(8), anchor="w")
        err.pack(fill="x", padx=18, pady=(8, 0))

        btns = tk.Frame(pad, bg=BG)
        btns.pack(fill="x", padx=18, pady=(16, 16))

        def cancel(_e=None) -> None:
            self.root.unbind("<Escape>")
            shade.destroy()
            self._opt_overlay = None
            self._resume_hotkeys()

        def save() -> None:
            folder = path_var.get().strip()
            if folder:
                resolved = Path(folder).expanduser()
                if not resolved.is_dir():
                    err.config(text=t("options_bad_path"))
                    return
                folder = str(resolved)
            save_config({
                "lang": lang_var.get(),
                "journal_dir": folder,
                "eddn_enabled": bool(eddn_var.get()),
                "inara_api_key": inara_var.get().strip(),
            })
            self.root.unbind("<Escape>")
            shade.destroy()
            self._opt_overlay = None
            _relaunch()

        _outline_btn(btns, t("options_save"), save)
        _outline_btn(btns, t("options_cancel"), cancel)
        self.root.bind("<Escape>", cancel)
        entry.focus_set()

    def run(self) -> None:
        self.root.mainloop()


class RankRail(tk.Canvas):
    def __init__(self, parent, *, mirror: bool = False, ranks: list | None = None) -> None:
        super().__init__(parent, width=152, bg=BG, highlightthickness=0, bd=0)
        self.snap: dict = {}
        self.mirror = mirror
        self.ranks = ranks if ranks is not None else RANKS
        self.bind("<Configure>", lambda _e: self.redraw())

    def set_snap(self, snap: dict) -> None:
        self.snap = snap
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        h = max(self.winfo_height(), 200)
        w = max(self.winfo_width(), 152)
        pad_top, pad_bot = 10, 42
        usable = h - pad_top - pad_bot
        if usable < 80:
            return
        table = self.ranks
        n = len(table)
        last = n - 1
        rid = self.snap.get("rank_id")
        frac = float(self.snap.get("frac") or 0)
        x = 10 if self.mirror else w - 10
        tick = 1 if self.mirror else -1

        self.create_line(x, pad_top, x, pad_top + usable, fill=CYAN_DEEP, width=1)
        if rid is not None:
            pos = min(last, max(0.0, rid + frac))
            y_now = pad_top + usable * (1 - pos / last)
            self.create_line(x, y_now, x, pad_top + usable, fill=CYAN, width=2)

        for i, row in enumerate(table):
            y = pad_top + usable * (1 - i / last)
            current = rid == i
            reached = rid is not None and i < rid
            if current:
                color = TEXT
                amount_color = CYAN_HI
                self.create_line(x + tick * 6, y, x + tick * 16, y, fill=CYAN, width=2)
                self.create_oval(x - 6, y - 6, x + 6, y + 6, fill=CYAN, outline=CYAN)
                self.create_oval(x - 2, y - 2, x + 2, y + 2, fill=TEXT, outline=TEXT)
            elif reached:
                color = CYAN
                amount_color = CYAN_DIM
                r = 3
                self.create_oval(x - r, y - r, x + r, y + r, fill=color, outline=color)
            else:
                color = MUTED
                amount_color = "#3a5560"
                r = 2
                self.create_oval(x - r, y - r, x + r, y + r, fill=color, outline=color)
            name_size = 10 if current else 8
            amt_size = 9 if current else 8
            tx = x + tick * 16
            anchor = "w" if self.mirror else "e"
            self.create_text(
                tx, y - 6 if current else y - 5,
                text=rank_short(row), fill=color, anchor=anchor,
                font=_font(name_size, "bold" if current else "normal"),
            )
            self.create_text(
                tx, y + 7 if current else y + 6,
                text=fmt_threshold(row["cr"], row["approx"]),
                fill=amount_color, anchor=anchor,
                font=_font(amt_size, "bold" if current else "normal"),
            )

        if rid is not None:
            pos = min(last, max(0.0, rid + frac))
            y = pad_top + usable * (1 - pos / last)
            if self.mirror:
                self.create_polygon(
                    x + 9, y, x + 2, y - 5, x + 2, y + 5,
                    fill=CYAN_HI, outline="",
                )
            else:
                self.create_polygon(
                    x - 9, y, x - 2, y - 5, x - 2, y + 5,
                    fill=CYAN_HI, outline="",
                )

        foot_x = 4 if self.mirror else w - 4
        foot_anchor = "w" if self.mirror else "e"
        nxt = self.snap.get("next")
        remain = self.snap.get("remain")
        if nxt:
            name = f"{nxt} :"
            extra = t("still", amount=fmt_credits(remain)) if remain is not None else "—"
        else:
            name = self.snap.get("name") or "Rang"
            extra = t("max")
        self.create_text(
            foot_x, h - 26, text=name, fill=TEXT,
            font=_font(9, "bold"), anchor=foot_anchor,
        )
        self.create_text(
            foot_x, h - 11,
            text=extra,
            fill=CYAN, font=_font(7, "bold"), anchor=foot_anchor,
        )


def run_gui(journal_dir: str | None = None) -> None:
    ScanDeckHud(journal_dir).run()
