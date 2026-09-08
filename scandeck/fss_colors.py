"""Couleurs FSS Elite Dangerous (barre d’analyse spectrale + classes stellaires)."""

from __future__ import annotations

from .models import BodyState

# Planètes : pastilles de la barre FSS (gauche → droite), calées sur le jeu.
# Astéroïdes (blanc) volontairement absents — ignorés dans la liste.
PLANET_FSS = {
    "Metal rich body": "#c9b56b",
    "High metal content body": "#7a7368",
    "Rocky body": "#8b929a",
    "Icy body": "#6ad4e6",
    "Rocky ice body": "#7ab8c8",
    "Earthlike body": "#2f9e58",
    "Water world": "#1e4ea8",
    "Ammonia world": "#8fa63a",
    "Water giant": "#2a6aa8",
    "Water giant with life": "#2a7ab0",
    "Gas giant with water based life": "#e09228",
    "Gas giant with ammonia based life": "#d4a030",
    "Sudarsky class I gas giant": "#e09228",
    "Sudarsky class II gas giant": "#e09228",
    "Sudarsky class III gas giant": "#d88820",
    "Sudarsky class IV gas giant": "#c87818",
    "Sudarsky class V gas giant": "#b86814",
    "Helium rich gas giant": "#c9a04a",
    "Helium gas giant": "#c9a04a",
}

# Étoiles : couleurs apparentes Elite (carte / FSS), séquence O→Y.
STAR_LETTER = {
    "O": "#6b8cff",
    "B": "#8fb0ff",
    "A": "#e4ecff",
    "F": "#fff6d8",
    "G": "#ffe14a",
    "K": "#ff9f40",
    "M": "#ff5a3c",
    "L": "#c44e24",
    "T": "#8a3a18",
    "Y": "#5a2810",
}

FALLBACK = "#5e8494"


def star_fss_color(star_class: str | None, spectral: str | None = None) -> str:
    raw = (star_class or spectral or "").strip()
    u = raw.upper().replace(" ", "")
    if not u:
        return FALLBACK
    if "BLACKHOLE" in u or u == "H":
        return "#3a3a55"
    if u == "N" or "NEUTRON" in u:
        return "#5ad2ff"
    if u.startswith("AEBE"):
        return "#9ec9ff"
    if u.startswith("TTS"):
        return "#ff8a5c"
    if u.startswith("A_") or u.startswith("B_"):
        return "#9bb8ff"
    if u.startswith("F_") or u.startswith("G_"):
        return "#fff0a8"
    if u.startswith("K_"):
        return "#ffb347"
    if u.startswith("M_"):
        return "#ff6a45"
    if u.startswith(("WN", "WC", "WO", "WNC")) or u == "W":
        return "#ff6ec7"
    if u == "D" or u.startswith(("DA", "DB", "DO", "DQ", "DC", "DX")):
        return "#dce6ff"
    if u == "C" or u.startswith(("CS", "CN", "CJ", "CH")):
        return "#ff4d1a"
    if u.startswith("MS") or u == "S":
        return "#ff7040"
    if u.startswith("X"):
        return "#b388ff"
    return STAR_LETTER.get(u[0], FALLBACK)


def planet_fss_color(planet_class: str | None) -> str:
    if not planet_class:
        return FALLBACK
    return PLANET_FSS.get(planet_class, FALLBACK)


def fss_color(body: BodyState) -> str:
    if body.star_type and not body.planet_class:
        return star_fss_color(getattr(body, "star_class", None), body.star_type)
    return planet_fss_color(body.planet_class)
