#!/usr/bin/env python3
"""Compile data/species.json from BioScan values + SrvSurvey criteria summaries."""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULESETS = Path("/tmp/edbio-src/rulesets")
CRITERIA = ROOT / "data" / "criteria"
OUT = ROOT / "data" / "species.json"

# Canonn Vista Genomics prices that differ from BioScan, or that we treat as canonical.
CANONN_OVERRIDES = {
    "Concha Biconcavis": 19_010_800,
}

QUERY_RE = re.compile(
    r"^\s*(?P<prop>[A-Za-z]+)\s*(?P<op>[&$!])?\[(?P<body>[^\]]*)\]\s*$"
)
RANGE_RE = re.compile(r"^\s*(?P<lo>[-0-9.]+)?\s*~\s*(?P<hi>[-0-9.]+)?\s*$")


def extract_bioscan(path: Path) -> list[dict]:
    src = path.read_text(encoding="utf-8")
    parts = re.split(r"('\$Codex_Ent_[^']+_Name;')\s*:", src)
    items = []
    i = 1
    while i < len(parts) - 1:
        key = parts[i].strip("'")
        body = parts[i + 1]
        if "Genus" in key:
            i += 2
            continue
        mname = re.search(r"'name'\s*:\s*'([^']+)'", body)
        mval = re.search(r"'value'\s*:\s*(\d+)", body)
        if mname and mval:
            items.append(
                {
                    "codex_species": key,
                    "name": mname.group(1),
                    "value_cr": int(mval.group(1)),
                }
            )
        i += 2
    return items


def parse_clause(raw: str) -> dict | None:
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
    if rng and prop in {"temp", "gravity", "pressure", "dist", "nebulae"}:
        lo = float(rng.group("lo")) if rng.group("lo") else None
        hi = float(rng.group("hi")) if rng.group("hi") else None
        return {"prop": prop, "kind": "range", "min": lo, "max": hi}
    if prop == "atmosComp":
        return {"prop": prop, "kind": "comp", "raw": body}
    values = [v.strip() for v in body.split(",") if v.strip()]
    kind = {"&": "all", "$": "all", "!": "not"}.get(op, "is")
    return {"prop": prop, "kind": kind, "values": values}


def walk_summaries(node: dict, acc: list, inherited: list[str]) -> None:
    queries = inherited + list(node.get("query") or [])
    if "species" in node:
        acc.append((node["species"], queries))
    children = list(node.get("children") or [])
    for child in children:
        walk_summaries(child, acc, queries)


def summarize_queries(query_lists: list[list[str]]) -> dict:
    bodies: set[str] = set()
    atmos: set[str] = set()
    temps: list[float] = []
    gravs: list[float] = []
    volcanism_none = False
    volcanism_some = False
    volcanism_types: set[str] = set()
    regions: set[str] = set()
    notes: list[str] = []

    for queries in query_lists:
        tmin = tmax = gmin = gmax = None
        for raw in queries:
            cl = parse_clause(raw)
            if not cl:
                continue
            if cl["prop"] == "body" and cl["kind"] == "is":
                bodies.update(cl["values"])
            elif cl["prop"] == "atmosType" and cl["kind"] == "is":
                atmos.update(cl["values"])
            elif cl["prop"] == "temp" and cl["kind"] == "range":
                if cl["min"] is not None:
                    tmin = cl["min"] if tmin is None else min(tmin, cl["min"])
                    temps.append(cl["min"])
                if cl["max"] is not None:
                    tmax = cl["max"] if tmax is None else max(tmax, cl["max"])
                    temps.append(cl["max"])
            elif cl["prop"] == "gravity" and cl["kind"] == "range":
                if cl["min"] is not None:
                    gmin = cl["min"]
                    gravs.append(cl["min"])
                if cl["max"] is not None:
                    gmax = cl["max"]
                    gravs.append(cl["max"])
            elif cl["prop"] == "volcanism":
                vals = cl.get("values") or []
                if "None" in vals:
                    volcanism_none = True
                if "Some" in vals:
                    volcanism_some = True
                for v in vals:
                    if v not in {"None", "Some"}:
                        volcanism_types.add(v)
                        volcanism_some = True
            elif cl["prop"] == "regions":
                regions.update(cl.get("values") or [])
            elif cl["prop"] == "nebulae":
                notes.append("Distance à une nébuleuse requise (empirique, incertaine si non calculée).")

    volcano = "unknown"
    if volcanism_none and not volcanism_some and not volcanism_types:
        volcano = "none"
    elif volcanism_some and not volcanism_none:
        volcano = "required"
    elif volcanism_none or volcanism_types:
        volcano = "variable"

    body_map = {
        "HMC": "High metal content body",
        "Rocky": "Rocky body",
        "RockyIce": "Rocky ice body",
        "Icy": "Icy body",
        "MRB": "Metal rich body",
    }
    return {
        "planet_types": sorted(body_map.get(b, b) for b in bodies) or None,
        "atmospheres": sorted(atmos) or None,
        "temp_min_k": min(temps) if temps else None,
        "temp_max_k": max(temps) if temps else None,
        "gravity_min_g": min(gravs) if gravs else None,
        "gravity_max_g": max(gravs) if gravs else None,
        "volcanism": volcano,
        "regions_empirical": sorted(regions) or None,
        "notes": sorted(set(notes)) or None,
        "constraint_certainty": "empirical",
        "constraint_source": "SrvSurvey bio-criteria (Spansh/Canonn observations)",
    }


def load_criteria_summaries() -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    grouped: dict[tuple[str, str], list[list[str]]] = defaultdict(list)
    for path in CRITERIA.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        genus = data.get("genus")
        if not genus:
            continue
        acc: list[tuple[str, list[str]]] = []
        walk_summaries(data, acc, list(data.get("query") or []))
        for species, queries in acc:
            grouped[(genus, species)].append(queries)
    for key, lists in grouped.items():
        out[key] = summarize_queries(lists)
    return out


def main() -> int:
    if not RULESETS.exists():
        print(f"BioScan rulesets introuvables : {RULESETS}", file=sys.stderr)
        print("Relancer le téléchargement ou compiler depuis data/species.json existant.", file=sys.stderr)
        return 1

    bioscan: dict[str, dict] = {}
    for path in sorted(RULESETS.glob("*.py")):
        for item in extract_bioscan(path):
            name = item["name"]
            if name == "Stratum Aranaemus":
                continue
            bioscan[name] = item

    summaries = load_criteria_summaries()
    genera_meta = json.loads((ROOT / "data" / "genera.json").read_text(encoding="utf-8"))["genera"]

    species = []
    for name, item in bioscan.items():
        genus = name.split(" ", 1)[0]
        short = name.split(" ", 1)[1] if " " in name else name
        value = CANONN_OVERRIDES.get(name, item["value_cr"])
        gmeta = genera_meta.get(genus, {})
        constraints = summaries.get((genus, short), {
            "constraint_certainty": "unknown",
            "notes": ["Conditions SrvSurvey non trouvées pour cette espèce."],
        })
        species.append(
            {
                "genus": genus,
                "name": name,
                "species_short": short,
                "codex_species": item["codex_species"],
                "value_cr": value,
                "first_logged_cr": value * 5,
                "colony_range_m": gmeta.get("colony_range_m"),
                "spotting": gmeta.get("spotting", "unknown"),
                "family": gmeta.get("family", "odyssey"),
                "constraints": constraints,
            }
        )

    species.sort(key=lambda s: (-s["value_cr"], s["name"]))
    payload = {
        "version": 1,
        "sorted_by": "value_cr_desc",
        "first_logged_multiplier": 5,
        "sources": [
            "Canonn Vista Genomics Price List",
            "EDMC-BioScan rulesets (names, Codex IDs, cross-check values)",
            "SrvSurvey bio-criteria (empirical spawn ranges)",
        ],
        "species": species,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(species)} species to {OUT}")
    assert next(s for s in species if s["name"] == "Stratum Tectonicas")["value_cr"] == 19_010_800
    assert next(s for s in species if s["name"] == "Tubus Compagibus")["value_cr"] == 7_774_700
    assert next(s for s in species if s["name"] == "Bacterium Aurasus")["value_cr"] == 1_000_000
    print("Control values OK: Tectonicas, Compagibus, Aurasus")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
