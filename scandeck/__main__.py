from __future__ import annotations

import argparse
from pathlib import Path

from .app import run_live, run_replay
from .catalog import Catalog
from .config import load as load_config
from .display import fmt_mcr
from .gui import run_gui
from .i18n import init_from_env, t
from .journal import latest_journal, resolve_journal_dir
from .matcher import TIER_ICON, value_tier


def main(argv: list[str] | None = None) -> int:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--lang", default=None)
    pre_args, _rest = pre.parse_known_args(argv)
    cfg = load_config()
    lang = pre_args.lang if pre_args.lang is not None else (cfg.get("lang") or "auto")
    init_from_env(lang)

    parser = argparse.ArgumentParser(
        prog="scandeck",
        description=t("app_desc"),
    )
    parser.add_argument("--journal-dir", default=None, help=t("journal_dir"))
    parser.add_argument(
        "--lang", default=None, choices=["auto", "en", "fr", "es"],
        help=t("lang"),
    )
    parser.add_argument("--cli", action="store_true", help=t("cli"))
    parser.add_argument("--gui", action="store_true", help=t("gui"))
    sub = parser.add_subparsers(dest="cmd")
    sub.required = False

    sub.add_parser("watch", help=t("watch_help"))

    replay = sub.add_parser("replay", help=t("replay_help"))
    replay.add_argument("files", nargs="*", type=Path)
    replay.add_argument("--latest", action="store_true", help=t("latest_help"))

    cat = sub.add_parser("catalog", help=t("catalog_help"))
    cat.add_argument("--genus", default=None)

    args = parser.parse_args(argv)
    if args.lang:
        init_from_env(args.lang)
    cmd = args.cmd or "watch"

    if cmd == "catalog":
        catalog = Catalog()
        rows = catalog.species
        if args.genus:
            resolved = catalog.resolve_genus(args.genus) or args.genus
            rows = [s for s in rows if s.genus.lower() == resolved.lower()]
        for s in rows:
            icon = TIER_ICON[value_tier(s)]
            print(
                f"{icon} {catalog.display_species(s.name):28} {fmt_mcr(s.value_cr):>12}  "
                f"→ {fmt_mcr(s.first_logged_cr):>12}  {s.colony_range_m} m  {s.spotting}"
            )
        print(f"\n{t('species_count', n=len(rows))}")
        return 0

    if cmd == "replay":
        files = list(args.files)
        if args.latest or not files:
            journal_dir = resolve_journal_dir(args.journal_dir)
            latest = latest_journal(journal_dir)
            if latest is None:
                raise SystemExit(t("no_journal"))
            files = [latest]
        run_replay(files)
        return 0

    if args.cli:
        run_live(getattr(args, "journal_dir", None))
    else:
        run_gui(getattr(args, "journal_dir", None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
