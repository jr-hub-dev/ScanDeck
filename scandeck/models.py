from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Certainty(str, Enum):
    CERTAIN = "certain"
    PLAUSIBLE = "plausible"
    INCOMPATIBLE = "incompatible"


class ScanProgress(str, Enum):
    NONE = "none"
    LOG = "log"
    SAMPLE = "sample"
    ANALYSE = "analyse"


@dataclass
class Species:
    genus: str
    name: str
    species_short: str
    codex_species: str
    value_cr: int
    first_logged_cr: int
    colony_range_m: int | None
    spotting: str
    family: str
    constraints: dict[str, Any]


@dataclass
class BodyState:
    system_name: str = ""
    system_address: int | None = None
    body_name: str = ""
    body_id: int | None = None
    planet_class: str | None = None
    atmosphere: str | None = None
    atmosphere_type: str | None = None
    atmosphere_composition: dict[str, float] = field(default_factory=dict)
    volcanism: str = ""
    temperature_k: float | None = None
    gravity_g: float | None = None
    pressure_atm: float | None = None
    materials: dict[str, float] = field(default_factory=dict)
    distance_ls: float | None = None
    landable: bool | None = None
    bio_count: int | None = None
    geo_count: int | None = None
    dss_genuses: list[str] = field(default_factory=list)
    dss_complete: bool = False
    star_types: list[str] = field(default_factory=list)
    parent_star_id: int | None = None
    parent_star: str | None = None
    displayed_signature: str | None = None
    last_ts: str = ""
    star_type: str | None = None
    star_class: str | None = None
    terraformable: bool = False
    mass_em: float | None = None
    was_discovered: bool | None = None
    was_mapped: bool | None = None
    was_footfalled: bool | None = None
    mapped: bool = False
    stellar_mass: float | None = None

    def key(self) -> tuple[int | None, int | None, str]:
        return (self.system_address, self.body_id, self.body_name)


@dataclass
class OrganicProgress:
    genus: str
    species_name: str
    variant: str | None = None
    stage: ScanProgress = ScanProgress.NONE
    sample_count: int = 0

    @property
    def complete(self) -> bool:
        return self.stage == ScanProgress.ANALYSE


@dataclass
class MatchResult:
    species: Species
    certainty: Certainty
    reasons: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    progress: OrganicProgress | None = None
