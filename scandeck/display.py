from __future__ import annotations

import sys

from .i18n import game_name, t
from .matcher import TIER_ICON, value_tier, verdict
from .fss_colors import fss_color
from .scan_value import fmt_scan_cr, map_estimate
from .models import BodyState, Certainty, MatchResult, OrganicProgress, ScanProgress


def _spotted(match: MatchResult) -> bool:
    return bool(match.progress and match.progress.species_name)


def _variant_label(progress: OrganicProgress | None) -> str:
    if not progress or not progress.variant:
        return ""
    text = progress.variant
    if " - " in text:
        return text.split(" - ", 1)[1].strip()
    return text


def _stage(match: MatchResult) -> ScanProgress:
    if match.progress is None:
        return ScanProgress.NONE
    return match.progress.stage


def scan_status_line(progress: OrganicProgress | None) -> str:
    if progress is None or progress.stage == ScanProgress.NONE:
        return t("scan_none")
    if progress.stage == ScanProgress.LOG:
        return t("scan_log")
    if progress.stage == ScanProgress.SAMPLE:
        return t("scan_sample")
    return t("scan_analyse")


def fmt_mcr(value: int) -> str:
    millions = value / 1_000_000
    from .i18n import decimal_sep
    text = f"{millions:.2f}".replace(".", decimal_sep())
    return f"{text} M Cr"


def fmt_mcr_range(lo: int, hi: int) -> str:
    if lo == hi:
        return fmt_mcr(lo)
    return f"{fmt_mcr(lo)} – {fmt_mcr(hi)}"


def fmt_m_compact(lo: int, hi: int) -> str:
    """Fourchette courte pour la liste système (ex. 12–28 M)."""

    def one(value: int) -> str:
        millions = value / 1_000_000
        if millions >= 10:
            return f"{millions:.0f}"
        from .i18n import decimal_sep
        return f"{millions:.1f}".replace(".", decimal_sep())

    if not hi:
        return "—"
    if lo == hi:
        return f"{one(lo)} M"
    return f"{one(lo)}–{one(hi)} M"


def short_body_name(system: str, body: str) -> str:
    if not body:
        return "—"
    if system and body == system:
        return "A"
    if system and body.startswith(system):
        rest = body[len(system):].strip()
        return rest or "A"
    return body


def remaining_value_span(matches: list[MatchResult]) -> tuple[int, int, str]:
    """Min–max restant (somme par genre) et pastille du meilleur restant."""
    order = {"high": 0, "good": 1, "ok": 2, "low": 3, "muted": 4}
    lo = hi = 0
    best = "muted"
    any_remaining = False
    for members in _group_by_genus(matches):
        remaining = [m for m in members if not (m.progress and m.progress.complete)]
        if not remaining:
            continue
        any_remaining = True
        identified = [m for m in remaining if _stage(m) != ScanProgress.NONE or _spotted(m)]
        if identified:
            value = identified[0].species.value_cr
            glo, ghi = value, value
            tier = value_tier(identified[0].species)
        else:
            glo = min(m.species.value_cr for m in remaining)
            ghi = max(m.species.value_cr for m in remaining)
            tier = value_tier(max(remaining, key=lambda m: m.species.value_cr).species)
        lo += glo
        hi += ghi
        if order.get(tier, 9) < order.get(best, 9):
            best = tier
    if not any_remaining:
        if any(m.progress and m.progress.complete for m in matches):
            return 0, 0, "good"
        return 0, 0, "muted"
    return lo, hi, best


def _group_by_genus(matches: list[MatchResult]) -> list[list[MatchResult]]:
    """Une liste par genre DSS : une planète n’a qu’une espèce par genre."""
    groups: dict[str, list[MatchResult]] = {}
    order: list[str] = []
    for match in matches:
        if match.certainty == Certainty.INCOMPATIBLE:
            continue
        genus = match.species.genus
        if genus not in groups:
            groups[genus] = []
            order.append(genus)
        groups[genus].append(match)
    return [groups[g] for g in order]


def _row_from_genus(
    members: list[MatchResult],
    shown,
    display_genus,
) -> dict:
    identified = [m for m in members if _stage(m) != ScanProgress.NONE]
    if not identified:
        identified = [m for m in members if _spotted(m)]
    if identified:
        match = identified[0]
        color = _variant_label(match.progress)
        name = shown(match.species.name)
        if color:
            name = f"{name}  ·  {color}"
        alts = ""
        if _stage(match) == ScanProgress.NONE:
            alts = t("nomad_alt")
        return {
            "name": name,
            "tier": value_tier(match.species),
            "icon": TIER_ICON[value_tier(match.species)],
            "status": scan_status_line(match.progress),
            "stage": _stage(match).value,
            "value": fmt_mcr(match.species.value_cr),
            "first": fmt_mcr(match.species.first_logged_cr),
            "dist": match.species.colony_range_m,
            "hard": match.species.spotting == "hard" and _stage(match) != ScanProgress.ANALYSE,
            "alts": alts,
        }
    best = max(members, key=lambda m: m.species.value_cr)
    lo = min(m.species.value_cr for m in members)
    hi = max(m.species.value_cr for m in members)
    first_lo = min(m.species.first_logged_cr for m in members)
    first_hi = max(m.species.first_logged_cr for m in members)
    genus = display_genus(best.species.genus)
    if len(members) == 1:
        name = shown(best.species.name)
        alts = ""
    else:
        shorts = [
            shown(m.species.species_short or m.species.name)
            for m in sorted(members, key=lambda m: -m.species.value_cr)
        ]
        name = f"{genus}  —  {' / '.join(shorts)}"
        alts = t("n_possible", n=len(members))
    hard = all(m.species.spotting == "hard" for m in members)
    return {
        "name": name,
        "tier": value_tier(best.species),
        "icon": TIER_ICON[value_tier(best.species)],
        "status": scan_status_line(None),
        "stage": ScanProgress.NONE.value,
        "value": fmt_mcr_range(lo, hi),
        "first": fmt_mcr_range(first_lo, first_hi),
        "dist": best.species.colony_range_m,
        "hard": hard,
        "alts": alts,
    }


def planet_short(body: BodyState) -> str:
    kind = {
        "High metal content body": "HMC",
        "Rocky body": "Rocky",
        "Rocky ice body": "Rocky ice",
        "Icy body": "Icy",
        "Metal rich body": "MR",
    }.get(body.planet_class or "", body.planet_class or "?")
    atmos = body.atmosphere_type or "?"
    temp = f"{body.temperature_k:.0f} K" if body.temperature_k is not None else "? K"
    bios = f"{body.bio_count} BIOS" if body.bio_count is not None else "? BIOS"
    return f"{kind} {atmos} — {temp} — {bios}"


def render_body(body: BodyState, matches: list[MatchResult], *, alert: bool = False) -> str:
    lines: list[str] = []
    lines.append("=" * 42)
    if alert:
        lines.append(t("alert_land").strip())
        lines.append("=" * 42)
    lines.append(f"{body.system_name}  /  {body.body_name}")
    lines.append(planet_short(body))
    if body.gravity_g is not None:
        volc = body.volcanism.strip() or t("none")
        lines.append(t("volcanism", value=volc))
    if body.dss_genuses:
        lines.append("DSS : " + ", ".join(body.dss_genuses))
    lines.append("=" * 42)

    visible = [m for m in matches if m.certainty != Certainty.INCOMPATIBLE]
    if not visible:
        lines.append("Aucune espèce plausible avec les données actuelles.")
        lines.append("Les conditions compatibles ne prouvent jamais une espèce.")
    else:
        def _shown(name: str) -> str:
            g = game_name("genus", "Tussock")
            return name.replace("Tussock", g).replace("Touradon", g)

        rows = [_row_from_genus(g, _shown, _shown) for g in _group_by_genus(visible)]
        todo = [r for r in rows if r["stage"] == ScanProgress.NONE.value]
        ongoing = [r for r in rows if r["stage"] in {ScanProgress.LOG.value, ScanProgress.SAMPLE.value}]
        done = [r for r in rows if r["stage"] == ScanProgress.ANALYSE.value]
        bio_total = body.bio_count if body.bio_count else len(rows)
        lines.append(
            f"SCANS  {len(done)}/{bio_total} terminée(s)"
            + (f"  ·  {len(ongoing)} en cours" if ongoing else "")
            + (f"  ·  {len(todo)} à faire" if todo else "")
        )
        lines.append("")

        def emit(title: str, rows: list[dict]) -> None:
            if not rows:
                return
            lines.append(title)
            for row in rows:
                hard = "  (difficile à voir)" if row.get("hard") else ""
                dist = f"  {row['dist']} m" if row.get("dist") else ""
                lines.append(f"  {row['status']}  {row['icon']} {row['name']}{hard}")
                lines.append(
                    f"     {row['value']}  →  {row['first']} First Logged{dist}"
                )
                if row.get("alts"):
                    lines.append(f"     {row['alts']}")
            lines.append("")

        emit(f"── {t('section_todo')} ──", todo)
        emit(f"── {t('section_ongoing')} ──", ongoing)
        emit(f"── {t('section_done')} ──", done)

        visible_genera = {m.species.genus.lower() for m in visible}
        unmatched = []
        for raw in body.dss_genuses:
            key = raw.lower()
            if key == "touradon":
                key = "tussock"
            if key not in visible_genera and not any(key in g or g in key for g in visible_genera):
                unmatched.append(raw)
        if unmatched:
            lines.append(
                "Genre DSS sans espèce dans les plages empiriques : " + ", ".join(unmatched)
            )

    text, _, _ = verdict(matches, body)
    lines.append("")
    lines.append(f"VERDICT : {text}")
    lines.append("")
    return "\n".join(lines)


def snapshot_body(body: BodyState, matches: list[MatchResult], *, alert: bool = False, catalog=None) -> dict:
    """Vue structurée pour le HUD (thread-safe : primitives seulement)."""
    visible = [m for m in matches if m.certainty != Certainty.INCOMPATIBLE]
    verdict_text, _, verdict_tone = verdict(matches, body)

    def shown(name: str) -> str:
        if catalog is None:
            g = game_name("genus", "Tussock")
            return name.replace("Tussock", g).replace("Touradon", g)
        return catalog.display_species(name)

    def genus_label(name: str) -> str:
        if catalog is None:
            g = game_name("genus", "Tussock")
            return name.replace("Tussock", g).replace("Touradon", g)
        return catalog.display_genus(name)

    rows = [_row_from_genus(g, shown, genus_label) for g in _group_by_genus(visible)]
    todo = [r for r in rows if r["stage"] == ScanProgress.NONE.value]
    ongoing = [r for r in rows if r["stage"] in {ScanProgress.LOG.value, ScanProgress.SAMPLE.value}]
    done = [r for r in rows if r["stage"] == ScanProgress.ANALYSE.value]
    bio_total = body.bio_count if body.bio_count else len(rows)

    dss = list(body.dss_genuses)
    if catalog:
        dss = [catalog.display_genus(g) for g in dss]

    return {
        "system": body.system_name,
        "body": body.body_name,
        "body_id": body.body_id,
        "summary": planet_short(body),
        "gravity": None if body.gravity_g is None else round(body.gravity_g, 2),
        "volcanism": (body.volcanism or "").strip() or t("none"),
        "dss": dss,
        "done": len(done),
        "total": bio_total or 0,
        "alert": alert,
        "verdict": verdict_text,
        "verdict_tone": verdict_tone,
        "todo": todo,
        "ongoing": ongoing,
        "done_rows": done,
        "pre_dss": False,
    }


def stub_snapshot(body: BodyState, matches: list[MatchResult] | None = None) -> dict:
    """Détail avant DSS : résumé planète / étoile, pas les cartes d'espèces."""
    if body.star_type and not body.planet_class:
        spec = body.star_type
        return {
            "system": body.system_name,
            "body": body.body_name,
            "body_id": body.body_id,
            "kind": "star",
            "summary": t("star_summary", spec=spec),
            "gravity": None,
            "volcanism": "",
            "dss": [],
            "done": 0,
            "total": 0,
            "alert": False,
            "verdict": t("star_verdict", spec=spec),
            "verdict_tone": "muted",
            "todo": [],
            "ongoing": [],
            "done_rows": [],
            "pre_dss": True,
        }
    lo, hi, _tier = remaining_value_span(matches or [])
    extra = fmt_m_compact(lo, hi) if hi else ""
    if body.landable is False:
        verdict_text = t("skip_unlandable")
        tone = "low"
    elif body.bio_count == 0:
        verdict_text = t("skip_no_bio")
        tone = "low"
    elif body.bio_count:
        verdict_text = f'{t("dss_for_genera")}  ·  {extra}' if extra else t("dss_for_genera")
        tone = "muted"
    else:
        verdict_text = t("scan_fss_signals")
        tone = "muted"
    summary = planet_short(body) if body.planet_class else (
        f"{body.bio_count} BIOS · FSS" if body.bio_count else "FSS"
    )
    return {
        "system": body.system_name,
        "body": body.body_name,
        "body_id": body.body_id,
        "kind": "planet",
        "summary": summary,
        "gravity": None if body.gravity_g is None else round(body.gravity_g, 2),
        "volcanism": (body.volcanism or "").strip() or t("none"),
        "dss": [],
        "done": 0,
        "total": body.bio_count or 0,
        "alert": False,
        "verdict": verdict_text,
        "verdict_tone": tone,
        "todo": [],
        "ongoing": [],
        "done_rows": [],
        "pre_dss": True,
    }


def snapshot_system_row(
    body: BodyState,
    matches: list[MatchResult],
    *,
    catalog=None,
    progress: dict | None = None,
) -> dict:
    if body.star_type and not body.planet_class:
        spec = body.star_type
        return {
            "body_id": body.body_id,
            "short": short_body_name(body.system_name, body.body_name),
            "name": body.body_name,
            "kind": "star",
            "bios": 0,
            "lo": 0,
            "hi": 0,
            "value": spec,
            "line2": spec,
            "tier": "muted",
            "icon": "",
            "status": t("star_status"),
            "done": False,
            "landable": None,
            "fss_color": fss_color(body),
            "map_cr": 0,
            "map_tier": "muted",
            "map_label": "",
            "mapped": False,
            "prior": "",
            "detail": stub_snapshot(body, []),
        }
    done_n = sum(1 for o in (progress or {}).values() if o.complete)
    from_matches = sum(1 for m in matches if m.progress and m.progress.complete)
    done_n = max(done_n, from_matches)
    total = body.bio_count or 0
    finished = bool(total and done_n >= total)
    lo, hi, tier = remaining_value_span(matches)
    kind_short = {
        "High metal content body": "HMC",
        "Rocky body": "Rocky",
        "Rocky ice body": "Rocky ice",
        "Icy body": "Icy",
        "Metal rich body": "MR",
        "Water world": "Water",
        "Ammonia world": "Ammonia",
        "Gas giant with water based life": "GG",
        "Sudarsky class I gas giant": "GG I",
        "Sudarsky class II gas giant": "GG II",
        "Sudarsky class III gas giant": "GG III",
        "Sudarsky class IV gas giant": "GG IV",
        "Sudarsky class V gas giant": "GG V",
        "Helium rich gas giant": "He GG",
        "Helium gas giant": "He GG",
        "Water giant": "Water GG",
        "Earthlike body": "ELW",
    }.get(body.planet_class or "", body.planet_class or t("planet_fallback"))
    map_cr, map_tier = map_estimate(body)
    map_label = fmt_scan_cr(map_cr) if map_cr else ""
    if total:
        if finished:
            status = "✓"
            lo, hi = 0, 0
        elif done_n:
            status = f"{done_n}/{total}" if total else str(done_n)
        elif body.dss_complete:
            status = "DSS"
        else:
            status = ""
    else:
        tier = map_tier
        if body.mapped or body.dss_complete:
            status = "✓"
        elif map_tier == "low":
            status = "skip"
        else:
            status = ""
    has_progress = bool(progress)
    if body.dss_complete or has_progress:
        _, alert, _ = verdict(matches, body)
        detail = snapshot_body(body, matches, alert=alert, catalog=catalog)
    else:
        detail = stub_snapshot(body, matches)
    value = fmt_m_compact(lo, hi)
    tf = " tf" if body.terraformable else ""
    if total:
        line2 = f"{total} bio" + (f" · {value}" if value != "—" else "")
    elif map_label:
        line2 = f"{kind_short}{tf} · {map_label}"
    else:
        line2 = f"{kind_short}{tf}"
    prior_bits = []
    if body.was_mapped is True:
        prior_bits.append("carto")
    if body.was_footfalled is True:
        prior_bits.append("FF")
    prior = " · ".join(prior_bits)
    return {
        "body_id": body.body_id,
        "short": short_body_name(body.system_name, body.body_name),
        "name": body.body_name,
        "kind": "planet",
        "bios": total,
        "lo": lo,
        "hi": hi,
        "value": value,
        "line2": line2,
        "tier": tier,
        "icon": TIER_ICON.get(tier, "") if (total or map_tier in {"high", "good"}) else "",
        "status": status,
        "done": finished,
        "landable": body.landable,
        "fss_color": fss_color(body),
        "map_cr": map_cr,
        "map_tier": map_tier,
        "map_label": map_label,
        "mapped": body.mapped or body.dss_complete,
        "prior": prior,
        "detail": detail,
    }


def snapshot_system(
    rows: list[dict],
    system_name: str,
    *,
    fss_body_count: int | None = None,
    fss_complete: bool = False,
    nsp_count: int = 0,
    nsp_items: list | None = None,
) -> dict:
    rank = {"high": 0, "good": 1, "ok": 2, "low": 3, "muted": 4}
    rows = sorted(
        rows,
        key=lambda r: (
            0 if r.get("kind") == "star" else (1 if r.get("bios") else 2),
            0 if r.get("map_tier") in {"high", "good"} and not r.get("mapped") else 1,
            rank.get(r.get("map_tier") or r.get("tier"), 5),
            -(r.get("map_cr") or 0),
            -(r.get("hi") or 0),
            -(r.get("bios") or 0),
            r.get("short") or "",
        ),
    )
    lo = sum(r.get("lo") or 0 for r in rows if not r.get("done") and r.get("bios"))
    hi = sum(r.get("hi") or 0 for r in rows if not r.get("done") and r.get("bios"))
    n = len(rows)
    n_bio = sum(1 for r in rows if r.get("bios"))
    if n_bio:
        header = t("header_bio_value", n=n_bio, value=fmt_m_compact(lo, hi)) if hi else t("header_bio", n=n_bio)
        empty = ""
    elif n and fss_body_count:
        header = t("header_bodies_fss", n=n, total=fss_body_count)
        empty = ""
    elif n:
        header = t("header_bodies", n=n)
        empty = ""
    elif fss_complete:
        header = t("header_fss_done")
        empty = t("empty_no_bio_sys")
    elif fss_body_count:
        header = t("header_fss_count", n=fss_body_count)
        empty = t("empty_honk_hint")
    else:
        header = t("header_no_bio")
        empty = t("empty_honk")
    items = list(nsp_items or [])
    if items:
        nsp_count = len(items)
    named = [str(it.get("name") or "").strip() for it in items if it.get("name")]
    leftover = nsp_count - len(named)
    lines = list(named)
    if leftover == 1:
        lines.append(t("nsp_one"))
    elif leftover > 1:
        lines.append(t("nsp_many", n=leftover))
    nsp_label = "\n".join(lines)
    return {
        "system": system_name,
        "system_bodies": rows,
        "bio_n": n,
        "sys_value": header,
        "sys_empty": empty,
        "fss_body_count": fss_body_count,
        "fss_complete": fss_complete,
        "nsp_count": nsp_count,
        "nsp_label": nsp_label,
    }


def print_block(text: str) -> None:
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()
