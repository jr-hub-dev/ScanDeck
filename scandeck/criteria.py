"""SrvSurvey bio-criteria query interpreter.

Species matching uses empirical observed ranges. A match is never 'certain'.
Unknown optional constraints (region, nebula, star) do not reject a species.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import BodyState

QUERY_RE = re.compile(
    r"^\s*(?P<prop>[A-Za-z]+)\s*(?P<op>[&$!])?\[(?P<body>[^\]]*)\]\s*$"
)
RANGE_RE = re.compile(r"^\s*(?P<lo>[-0-9.]+)?\s*~\s*(?P<hi>[-0-9.]+)?\s*$")

SOFT_PROPS = {"star", "parentStar", "primaryStar", "regions", "nebulae", "guardian"}

BODY_PREFIX = {
    "HMC": "high metal content",
    "Rocky": "rocky body",
    "RockyIce": "rocky ice",
    "Icy": "icy body",
    "MRB": "metal rich",
}


@dataclass
class Clause:
    raw: str
    prop: str
    kind: str
    values: list[str] | None = None
    min_v: float | None = None
    max_v: float | None = None
    comp: list[tuple[str, float]] | None = None


def parse_clause(raw: str) -> Clause | None:
    raw = raw.strip()
    if not raw or raw.startswith("#"):
        return None
    m = QUERY_RE.match(raw)
    if not m:
        return None
    prop = m.group("prop")
    op = m.group("op") or ""
    body = m.group("body").strip()
    rng = RANGE_RE.match(body)
    if rng and "~" in body:
        lo = float(rng.group("lo")) if rng.group("lo") else None
        hi = float(rng.group("hi")) if rng.group("hi") else None
        return Clause(raw=raw, prop=prop, kind="range", min_v=lo, max_v=hi)
    if prop == "atmosComp":
        parts = []
        for chunk in body.split("|"):
            chunk = chunk.strip()
            mm = re.match(r"(.+?)\s*>=\s*([0-9.]+)", chunk)
            if mm:
                parts.append((mm.group(1).strip(), float(mm.group(2))))
        return Clause(raw=raw, prop=prop, kind="comp", comp=parts)
    values = [v.strip() for v in body.split(",") if v.strip()]
    kind = {"&": "all", "$": "all", "!": "not"}.get(op, "is")
    return Clause(raw=raw, prop=prop, kind=kind, values=values)


def planet_kind(planet_class: str | None) -> str | None:
    if not planet_class:
        return None
    p = planet_class.lower()
    if "rocky ice" in p:
        return "RockyIce"
    if p.startswith("rocky"):
        return "Rocky"
    if "high metal" in p:
        return "HMC"
    if "metal rich" in p:
        return "MRB"
    if p.startswith("icy"):
        return "Icy"
    return planet_class


def _num_in_range(value: float | None, clause: Clause) -> bool | None:
    if value is None:
        return None
    if clause.min_v is not None and value < clause.min_v:
        return False
    if clause.max_v is not None and value > clause.max_v:
        return False
    return True


def _contains_ci(haystack: str, needle: str) -> bool:
    return needle.lower() in haystack.lower()


def evaluate_clause(clause: Clause, body: BodyState) -> bool | None:
    """True / False / None (unknown, treat as pass for species-level)."""
    prop = clause.prop
    if prop in SOFT_PROPS:
        if prop == "star":
            if not body.star_types:
                return None
            wanted = {v.lower() for v in clause.values or []}
            have = {s.lower() for s in body.star_types}
            if clause.kind == "not":
                return wanted.isdisjoint(have)
            return bool(wanted & have)
        return None

    if prop == "body":
        kind = planet_kind(body.planet_class)
        if kind is None:
            return None
        values = clause.values or []
        if clause.kind == "not":
            return kind not in values
        return kind in values

    if prop == "atmosType":
        if not body.atmosphere_type:
            return None
        have = body.atmosphere_type.lower()
        values = [v.lower() for v in clause.values or []]
        if clause.kind == "not":
            return have not in values
        return have in values

    if prop == "temp":
        return _num_in_range(body.temperature_k, clause)

    if prop == "gravity":
        return _num_in_range(body.gravity_g, clause)

    if prop == "pressure":
        return _num_in_range(body.pressure_atm, clause)

    if prop == "dist":
        return _num_in_range(body.distance_ls, clause)

    if prop == "volcanism":
        volc = (body.volcanism or "").strip()
        values = clause.values or []
        is_none = volc == "" or volc.lower() in {"none", "no volcanism"}
        ok = False
        for v in values:
            if v == "None":
                ok = ok or is_none
            elif v == "Some":
                ok = ok or (not is_none)
            else:
                ok = ok or (not is_none and _contains_ci(volc, v))
        if clause.kind == "not":
            return not ok
        return ok

    if prop == "atmosComp":
        if not body.atmosphere_composition:
            return None
        comps = {k.lower(): v for k, v in body.atmosphere_composition.items()}
        for name, minimum in clause.comp or []:
            got = comps.get(name.lower())
            if got is not None and got + 1e-6 >= minimum:
                return True
        return False

    if prop == "mats":
        if not body.materials:
            return None
        mats = {k.lower() for k in body.materials}
        wanted = {v.lower() for v in clause.values or []}
        if clause.kind == "all":
            return wanted <= mats
        if clause.kind == "not":
            return wanted.isdisjoint(mats)
        return bool(wanted & mats)

    if prop == "atmosphere":
        if not body.atmosphere:
            return None
        have = body.atmosphere.lower().replace(" atmosphere", "")
        values = [v.lower() for v in clause.values or []]
        return any(v in have for v in values)

    return None


class CriteriaEngine:
    def __init__(self, criteria_dir: Path) -> None:
        self.trees: dict[str, dict[str, Any]] = {}
        for path in criteria_dir.glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            genus = data.get("genus")
            if genus:
                self.trees[genus] = data

    def matching_species(self, body: BodyState, genera: list[str] | None = None) -> dict[str, list[str]]:
        """Return {genus: [species_short, ...]} that pass hard constraints."""
        wanted = set(genera) if genera else set(self.trees)
        found: dict[str, list[str]] = {}
        for genus, tree in self.trees.items():
            if genus not in wanted:
                continue
            hits = self._eval_node(tree, body, list(tree.get("query") or []), None)
            if hits:
                found[genus] = sorted(set(hits))
        return found

    def species_incompatible_reasons(self, tree: dict, species_short: str, body: BodyState) -> list[str]:
        reasons: list[str] = []
        node = self._find_species(tree, species_short)
        if node is None:
            return ["Espèce absente des critères"]
        queries = list(tree.get("query") or []) + list(node.get("query") or [])
        for raw in queries:
            cl = parse_clause(raw)
            if cl is None or cl.prop in SOFT_PROPS:
                continue
            result = evaluate_clause(cl, body)
            if result is False:
                reasons.append(cl.raw.strip())
        return reasons

    def _find_species(self, node: dict, name: str) -> dict | None:
        if node.get("species") == name:
            return node
        for child in node.get("children") or []:
            found = self._find_species(child, name)
            if found:
                return found
        return None

    def _eval_node(self, node: dict, body: BodyState, inherited: list[str], species: str | None) -> list[str]:
        queries = inherited + list(node.get("query") or [])
        species = node.get("species", species)

        if not self._hard_ok(queries, body):
            return []

        children = list(node.get("children") or [])
        if node.get("useCommonChildren"):
            return [species] if species else []

        if not children:
            return [species] if species else []

        hits: list[str] = []
        for child in children:
            hits.extend(self._eval_node(child, body, queries, species))
        if hits:
            return hits

        if species and all(c.get("variant") for c in children):
            only_soft = True
            for child in children:
                for raw in child.get("query") or []:
                    cl = parse_clause(raw)
                    if cl is not None and cl.prop not in SOFT_PROPS:
                        only_soft = False
                        break
            if only_soft:
                return [species]
        return []

    def _hard_ok(self, queries: list[str], body: BodyState) -> bool:
        for raw in queries:
            cl = parse_clause(raw)
            if cl is None or cl.prop in SOFT_PROPS:
                continue
            result = evaluate_clause(cl, body)
            if result is False:
                return False
        return True
