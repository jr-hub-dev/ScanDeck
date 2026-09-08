"""Valeur DSS estimée (formule MattG / EDDI).

base = k + k × 0,56591828 × masse_⊕^0,2
puis multiplicateurs cartographie, bonus Odyssey, efficacité, first discovery.

k dépend du type ; le bonus terraformable s’ajoute si le journal le dit
(ELW : toujours, c’est dans le barème).
On suppose un DSS efficace — c’est le gain si tu cartographies maintenant.
"""

from __future__ import annotations

from .models import BodyState

Q = 0.56591828
SCAN_POWER = 0.2
SCAN_MIN = 500.0
FIRST_DISCOVERY = 2.6
EFFICIENT_MAP = 1.25
MAP_FIRST_DISC_AND_MAP = 3.699622554
MAP_FIRST_MAP_ONLY = 8.0956
MAP_ALREADY = 3.3333333333
ODYSSEY_MAP = 0.3
ODYSSEY_MAP_FLOOR = 555.0

# k de base (journal PlanetClass).
_K: dict[str, int] = {
    "Metal rich body": 21790,
    "Ammonia world": 96932,
    "Sudarsky class I gas giant": 1656,
    "Sudarsky class II gas giant": 9654,
    "High metal content body": 9654,
    "Water world": 64831,
    "Earthlike body": 64831,
}
_K_DEFAULT = 300

# Bonus terraformable (100 % — le jeu a une échelle 0–100 % inconnue).
_K_TF: dict[str, int] = {
    "High metal content body": 100677,
    "Water world": 116295,
    "Earthlike body": 116295,
}
_K_TF_DEFAULT = 93328

MAP_HIGH = 500_000
MAP_GOOD = 100_000
MAP_OK = 50_000


def fmt_scan_cr(value: int) -> str:
    from .i18n import decimal_sep
    sep = decimal_sep()
    if value >= 1_000_000:
        n = value / 1_000_000
        text = f"{n:.1f}".replace(".", sep).rstrip("0").rstrip(sep)
        return f"{text} M"
    if value >= 1_000:
        return f"{value / 1_000:.0f} k"
    return str(value)


def _k(planet_class: str, terraformable: bool) -> int:
    k = _K.get(planet_class, _K_DEFAULT)
    # Les ELW embarquent le bonus « terraformable » du barème, même sans flag.
    if planet_class == "Earthlike body" or terraformable:
        k += _K_TF.get(planet_class, _K_TF_DEFAULT)
    return k


def body_value(
    planet_class: str,
    mass_em: float,
    *,
    terraformable: bool = False,
    first_discoverer: bool = False,
    first_mapper: bool = False,
    mapped: bool = True,
    efficient: bool = True,
    odyssey: bool = True,
) -> int:
    """Crédits UC estimés. `mapped=True` = tu DSS maintenant."""
    mass = max(float(mass_em), 1e-6)
    k = _k(planet_class, terraformable)
    # Bulle pré-Odyssey : first discoverer mais déjà cartographié par un autre.
    bubble = first_discoverer and not first_mapper

    mapping = 1.0
    if mapped:
        if first_discoverer and first_mapper:
            mapping = MAP_FIRST_DISC_AND_MAP
        elif first_mapper:
            mapping = MAP_FIRST_MAP_ONLY
        else:
            mapping = MAP_ALREADY

    value = max(SCAN_MIN, (k + k * Q * (mass ** SCAN_POWER)) * mapping)
    if mapped:
        if odyssey and not bubble:
            bonus = value * ODYSSEY_MAP
            value += bonus if bonus > ODYSSEY_MAP_FLOOR else ODYSSEY_MAP_FLOOR
        if efficient:
            value *= EFFICIENT_MAP
    if first_discoverer and not bubble:
        value *= FIRST_DISCOVERY
    return int(round(value))


def star_value(star_type: str, mass_sol: float, *, first_discoverer: bool = False) -> int:
    """Valeur FSS d'une étoile (MattG / EDDI)."""
    mass = max(float(mass_sol), 0.0)
    kind = (star_type or "").strip()
    if kind in {"H", "N"}:
        k = 22628.0
    elif kind.lower() == "supermassiveblackhole":
        k = 33.5678
    elif kind.startswith("D") and len(kind) <= 3:
        k = 14057.0
    else:
        k = 1200.0
    value = k + (mass * k / 66.25)
    if first_discoverer:
        value *= FIRST_DISCOVERY
    return int(round(max(SCAN_MIN, value)))


def carto_stock_value(body: BodyState) -> int:
    """Ce que UC paierait maintenant pour ce corps (FSS, ou DSS si déjà cartographié)."""
    first_disc = body.was_discovered is False
    if body.star_class and body.stellar_mass is not None and not body.planet_class:
        return star_value(body.star_class, body.stellar_mass, first_discoverer=first_disc)
    if not body.planet_class or body.mass_em is None:
        return 0
    mapped = bool(body.mapped or body.dss_complete)
    return body_value(
        body.planet_class,
        body.mass_em,
        terraformable=bool(body.terraformable),
        first_discoverer=first_disc,
        first_mapper=body.was_mapped is False,
        mapped=mapped,
        efficient=mapped,
        odyssey=True,
    )


def map_estimate(body: BodyState) -> tuple[int, str]:
    """Retourne (crédits DSS efficaces, palier high/good/ok/low). 0 si incalculable."""
    if not body.planet_class or body.mass_em is None:
        return 0, "muted"
    first_disc = body.was_discovered is False
    first_map = body.was_mapped is False
    value = body_value(
        body.planet_class,
        body.mass_em,
        terraformable=bool(body.terraformable),
        first_discoverer=first_disc,
        first_mapper=first_map,
        mapped=True,
        efficient=True,
        odyssey=True,
    )
    if value >= MAP_HIGH:
        tier = "high"
    elif value >= MAP_GOOD:
        tier = "good"
    elif value >= MAP_OK:
        tier = "ok"
    else:
        tier = "low"
    return value, tier
