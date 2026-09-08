"""Seuils de rang Exobiologiste (Vista Genomics, post Update 14)
et Explorateur (Universal Cartographics, wiki Elite Dangerous).

Sources exo : wiki / Aunty Sledge. Elite IV et V exo sont estimés.
Sources explo : wiki Explorer — Elite I–V Odyssey.
"""

from __future__ import annotations

RANKS: list[dict] = [
    {"id": 0, "en": "Directionless", "es": "Inexperto", "short_en": "Directionless", "short_es": "Inexp.", "fr": "Inexpérimenté", "short": "Inexp.", "cr": 0, "approx": False},
    {"id": 1, "en": "Mostly Directionless", "es": "Casi inexperto", "short_en": "Mostly Directionless", "short_es": "C. inexp.", "fr": "Plutôt inexpérimenté", "short": "P. inexp.", "cr": 22_500_000, "approx": False},
    {"id": 2, "en": "Compiler", "es": "Compilador", "short_en": "Compiler", "short_es": "Compilador", "fr": "Compilateur", "short": "Compilateur", "cr": 83_475_000, "approx": False},
    {"id": 3, "en": "Collector", "es": "Colector", "short_en": "Collector", "short_es": "Colector", "fr": "Collectionneur", "short": "Collectionneur", "cr": 210_560_000, "approx": False},
    {"id": 4, "en": "Cataloguer", "es": "Catalogador", "short_en": "Cataloguer", "short_es": "Catalogador", "fr": "Catalogueur", "short": "Catalogueur", "cr": 532_800_000, "approx": False},
    {"id": 5, "en": "Taxonomist", "es": "Taxonomista", "short_en": "Taxonomist", "short_es": "Taxonomista", "fr": "Taxonomiste", "short": "Taxonomiste", "cr": 1_144_000_000, "approx": False},
    {"id": 6, "en": "Ecologist", "es": "Ecologista", "short_en": "Ecologist", "short_es": "Ecologista", "fr": "Écologiste", "short": "Écologiste", "cr": 2_262_600_000, "approx": False},
    {"id": 7, "en": "Geneticist", "es": "Genetista", "short_en": "Geneticist", "short_es": "Genetista", "fr": "Généticien", "short": "Généticien", "cr": 3_996_000_000, "approx": False},
    {"id": 8, "en": "Elite", "es": "Elite", "short_en": "Elite", "short_es": "Elite", "fr": "Elite", "short": "Elite", "cr": 8_425_000_000, "approx": False},
    {"id": 9, "en": "Elite I", "es": "Elite I", "short_en": "Elite I", "short_es": "Elite I", "fr": "Elite I", "short": "Elite I", "cr": 12_969_000_000, "approx": False},
    {"id": 10, "en": "Elite II", "es": "Elite II", "short_en": "Elite II", "short_es": "Elite II", "fr": "Elite II", "short": "Elite II", "cr": 17_425_000_000, "approx": False},
    {"id": 11, "en": "Elite III", "es": "Elite III", "short_en": "Elite III", "short_es": "Elite III", "fr": "Elite III", "short": "Elite III", "cr": 21_925_000_000, "approx": False},
    {"id": 12, "en": "Elite IV", "es": "Elite IV", "short_en": "Elite IV", "short_es": "Elite IV", "fr": "Elite IV", "short": "Elite IV", "cr": 26_070_000_000, "approx": True},
    {"id": 13, "en": "Elite V", "es": "Elite V", "short_en": "Elite V", "short_es": "Elite V", "fr": "Elite V", "short": "Elite V", "cr": 30_553_600_000, "approx": True},
]

EXPLORE_RANKS: list[dict] = [
    {"id": 0, "en": "Aimless", "es": "Sin rumbo", "short_en": "Aimless", "short_es": "Sin rumbo", "fr": "Sans but", "short": "Sans but", "cr": 0, "approx": False},
    {"id": 1, "en": "Mostly Aimless", "es": "Casi sin rumbo", "short_en": "Mostly Aimless", "short_es": "C. s. rumbo", "fr": "P. sans but", "short": "P. s. but", "cr": 40_000, "approx": False},
    {"id": 2, "en": "Scout", "es": "Explorador", "short_en": "Scout", "short_es": "Explorador", "fr": "Éclaireur", "short": "Éclaireur", "cr": 270_000, "approx": False},
    {"id": 3, "en": "Surveyor", "es": "Topógrafo", "short_en": "Surveyor", "short_es": "Topógrafo", "fr": "Arpenteur", "short": "Arpenteur", "cr": 1_140_000, "approx": False},
    {"id": 4, "en": "Trailblazer", "es": "Abrecaminos", "short_en": "Trailblazer", "short_es": "Abrecaminos", "fr": "Pisteur", "short": "Pisteur", "cr": 4_200_000, "approx": False},
    {"id": 5, "en": "Pathfinder", "es": "Guía", "short_en": "Pathfinder", "short_es": "Guía", "fr": "Guide", "short": "Guide", "cr": 10_000_000, "approx": False},
    {"id": 6, "en": "Ranger", "es": "Guardabosques", "short_en": "Ranger", "short_es": "Guardab.", "fr": "Ranger", "short": "Ranger", "cr": 35_000_000, "approx": False},
    {"id": 7, "en": "Pioneer", "es": "Pionero", "short_en": "Pioneer", "short_es": "Pionero", "fr": "Pionnier", "short": "Pionnier", "cr": 116_000_000, "approx": False},
    {"id": 8, "en": "Elite", "es": "Elite", "short_en": "Elite", "short_es": "Elite", "fr": "Elite", "short": "Elite", "cr": 320_000_000, "approx": False},
    {"id": 9, "en": "Elite I", "es": "Elite I", "short_en": "Elite I", "short_es": "Elite I", "fr": "Elite I", "short": "Elite I", "cr": 640_000_000, "approx": False},
    {"id": 10, "en": "Elite II", "es": "Elite II", "short_en": "Elite II", "short_es": "Elite II", "fr": "Elite II", "short": "Elite II", "cr": 945_000_000, "approx": False},
    {"id": 11, "en": "Elite III", "es": "Elite III", "short_en": "Elite III", "short_es": "Elite III", "fr": "Elite III", "short": "Elite III", "cr": 1_255_400_000, "approx": False},
    {"id": 12, "en": "Elite IV", "es": "Elite IV", "short_en": "Elite IV", "short_es": "Elite IV", "fr": "Elite IV", "short": "Elite IV", "cr": 1_570_000_000, "approx": False},
    {"id": 13, "en": "Elite V", "es": "Elite V", "short_en": "Elite V", "short_es": "Elite V", "fr": "Elite V", "short": "Elite V", "cr": 1_884_000_000, "approx": False},
]


def fmt_credits(value: int | float | None) -> str:
    if value is None:
        return "?"
    n = float(value)
    from .i18n import decimal_sep
    sep = decimal_sep()
    if n >= 1_000_000_000:
        text = f"{n / 1_000_000_000:.2f}".replace(".", sep)
        return f"{text} Md" if sep == "," else f"{text} Bn"
    if n >= 1_000_000:
        text = f"{n / 1_000_000:.1f}".replace(".", sep)
        return f"{text} M"
    return f"{int(n):,} Cr".replace(",", " " if sep == "," else ",")


def fmt_threshold(value: int, approx: bool = False) -> str:
    """Montant court pour un palier de la frise."""
    if value <= 0:
        return "0"
    prefix = "~" if approx else ""
    if value >= 1_000_000_000:
        n = value / 1_000_000_000
        from .i18n import decimal_sep
        sep = decimal_sep()
        text = f"{n:.2f}".rstrip("0").rstrip(".").replace(".", sep)
        unit = "Md" if sep == "," else "B"
        return f"{prefix}{text} {unit}"
    n = value / 1_000_000
    if n >= 100:
        return f"{prefix}{n:.0f} M"
    from .i18n import decimal_sep
    text = f"{n:.1f}".replace(".", decimal_sep())
    return f"{prefix}{text} M"


def rank_name(row: dict) -> str:
    from .i18n import lang
    return row.get(lang()) or row.get("en") or row.get("fr") or ""


def rank_short(row: dict) -> str:
    from .i18n import lang
    code = lang()
    if code == "fr":
        return row.get("short") or row.get("fr") or ""
    if code == "es":
        return row.get("short_es") or row.get("es") or row.get("en") or ""
    return row.get("short_en") or row.get("en") or ""


def from_credits(profits: int | None, ranks: list[dict] | None = None) -> dict:
    """Position sur la frise à partir du profit cumulé."""
    table = ranks if ranks is not None else RANKS
    if profits is None or profits < 0:
        return {
            "rank_id": None,
            "frac": 0.0,
            "name": "—",
            "next": rank_name(table[0]),
            "remain": None,
            "profits": profits,
        }
    last = len(table) - 1
    if profits >= table[last]["cr"]:
        return {
            "rank_id": last,
            "frac": 1.0,
            "name": rank_name(table[last]),
            "next": None,
            "remain": 0,
            "profits": profits,
            "approx": table[last]["approx"],
        }
    idx = 0
    for i, row in enumerate(table):
        if profits >= row["cr"]:
            idx = i
    nxt = table[idx + 1]
    lo, hi = table[idx]["cr"], nxt["cr"]
    span = hi - lo
    frac = 0.0 if span <= 0 else max(0.0, min(0.999, (profits - lo) / span))
    return {
        "rank_id": idx,
        "frac": frac,
        "name": rank_name(table[idx]),
        "next": rank_name(nxt),
        "remain": max(0, hi - profits),
        "profits": profits,
        "approx": table[idx]["approx"] or nxt["approx"],
    }


def from_journal(
    rank_id: int | None,
    progress_pct: int | None,
    profits: int | None,
    ranks: list[dict] | None = None,
) -> dict:
    """Rang jeu + % ; les crédits affinent le reste à gagner si on les a."""
    table = ranks if ranks is not None else RANKS
    if rank_id is None:
        return from_credits(profits, table)
    idx = max(0, min(len(table) - 1, int(rank_id)))
    pct = 0 if progress_pct is None else max(0, min(100, int(progress_pct)))
    frac = 1.0 if idx == len(table) - 1 else pct / 100.0
    nxt = rank_name(table[idx + 1]) if idx < len(table) - 1 else None
    remain = None
    if idx < len(table) - 1:
        lo, hi = table[idx]["cr"], table[idx + 1]["cr"]
        if profits is not None and lo <= profits < hi:
            remain = max(0, hi - profits)
        else:
            remain = max(0, int(round((1.0 - frac) * (hi - lo))))
    elif idx == len(table) - 1:
        remain = 0
    return {
        "rank_id": idx,
        "frac": frac,
        "name": rank_name(table[idx]),
        "next": nxt,
        "remain": remain,
        "profits": profits,
        "approx": table[idx]["approx"] or (idx < len(table) - 1 and table[idx + 1]["approx"]),
        "game_progress": pct,
    }
