from __future__ import annotations

from .catalog import Catalog
from .criteria import CriteriaEngine
from .i18n import t
from .models import BodyState, Certainty, MatchResult, OrganicProgress, ScanProgress, Species


PRIORITY_HIGH = 10_000_000
PRIORITY_GOOD = 5_000_000
PRIORITY_OK = 2_000_000


def value_tier(species: Species) -> str:
    value = species.value_cr
    spotting = species.spotting
    if spotting == "hard" and value < 8_000_000:
        if value >= PRIORITY_GOOD:
            return "ok"
        if value >= PRIORITY_OK:
            return "low"
        return "low"
    if value >= PRIORITY_HIGH:
        return "high"
    if value >= PRIORITY_GOOD:
        return "good"
    if value >= PRIORITY_OK:
        return "ok"
    return "low"


TIER_ICON = {
    "high": "🔥",
    "good": "🟢",
    "ok": "🟡",
    "low": "🔴",
}


class Matcher:
    def __init__(self, catalog: Catalog, criteria: CriteriaEngine) -> None:
        self.catalog = catalog
        self.criteria = criteria

    def match(
        self,
        body: BodyState,
        progress: dict[str, OrganicProgress] | None = None,
    ) -> list[MatchResult]:
        progress = progress or {}
        dss_genera = [g for g in (self.catalog.resolve_genus(x) or x for x in body.dss_genuses) if g]
        predicted = self.criteria.matching_species(body, dss_genera or None)

        results: list[MatchResult] = []
        genera_to_show = dss_genera or list(predicted)
        confirmed_by_genus: dict[str, str] = {}
        for org in progress.values():
            if org.species_name:
                g = self.catalog.resolve_genus(org.genus) or org.genus
                confirmed_by_genus[g] = org.species_name

        for genus in genera_to_show:
            plausible_shorts = set(predicted.get(genus, []))
            for species in self.catalog.species_for_genus(genus):
                org = progress.get(species.name) or progress.get(species.codex_species)
                confirmed = confirmed_by_genus.get(genus)
                if confirmed and species.name != confirmed:
                    continue
                if org and org.complete:
                    results.append(
                        MatchResult(
                            species=species,
                            certainty=Certainty.CERTAIN,
                            reasons=[t("reason_analyse")],
                            progress=org,
                        )
                    )
                    continue
                if org and org.stage.value != "none":
                    results.append(
                        MatchResult(
                            species=species,
                            certainty=Certainty.CERTAIN,
                            reasons=[t("reason_sampler")],
                            progress=org,
                        )
                    )
                    continue
                if org and org.species_name:
                    results.append(
                        MatchResult(
                            species=species,
                            certainty=Certainty.CERTAIN,
                            reasons=[t("reason_nomad")],
                            progress=org,
                        )
                    )
                    continue
                if species.species_short in plausible_shorts:
                    reasons = [t("reason_ok")]
                    if dss_genera:
                        reasons.append(t("reason_dss", genus=genus))
                    else:
                        reasons.append(t("reason_no_dss"))
                    results.append(
                        MatchResult(
                            species=species,
                            certainty=Certainty.PLAUSIBLE,
                            reasons=reasons,
                            progress=org,
                        )
                    )

        results.sort(
            key=lambda r: (
                0 if r.certainty != Certainty.INCOMPATIBLE else 1,
                -r.species.value_cr,
                r.species.name,
            )
        )
        return results


def verdict(matches: list[MatchResult], body: BodyState) -> tuple[str, bool, str]:
    """Retourne (texte, alerte_haute_valeur, ton)."""
    visible = [m for m in matches if m.certainty != Certainty.INCOMPATIBLE]
    if not visible:
        if body.dss_genuses and body.bio_count:
            return t("verdict_no_match"), False, "ok"
        return t("verdict_no_bio"), False, "muted"

    progress_complete = [m for m in visible if m.progress and m.progress.complete]
    if body.bio_count and len(progress_complete) >= body.bio_count:
        return t("verdict_done"), False, "good"
    remaining = [m for m in visible if not (m.progress and m.progress.complete)]
    if not remaining and visible:
        return t("verdict_done"), False, "good"

    remaining_plausible = [m for m in remaining if m.certainty != Certainty.INCOMPATIBLE]
    tiers = {value_tier(m.species) for m in remaining_plausible}
    high_unstarted = any(
        value_tier(m.species) == "high" and (m.progress is None or m.progress.stage == ScanProgress.NONE)
        for m in remaining_plausible
    )
    if "high" in tiers:
        return t("verdict_high"), high_unstarted, "high"
    if "good" in tiers:
        hard_only = all(
            m.species.spotting == "hard"
            for m in remaining_plausible
            if value_tier(m.species) == "good"
        )
        if hard_only:
            return t("verdict_hard"), False, "ok"
        return t("verdict_good"), False, "good"
    if "ok" in tiers:
        return t("verdict_ok"), False, "ok"
    return t("verdict_skip"), False, "low"
