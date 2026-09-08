from __future__ import annotations

import json
from functools import cached_property
from pathlib import Path

from .models import Species
from .paths import resource_root

DATA_DIR = resource_root() / "data"


class Catalog:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or DATA_DIR
        species_raw = json.loads((self.data_dir / "species.json").read_text(encoding="utf-8"))
        genera_raw = json.loads((self.data_dir / "genera.json").read_text(encoding="utf-8"))
        fields = Species.__dataclass_fields__
        self.species: list[Species] = [
            Species(**{k: row[k] for k in fields if k in row})
            for row in species_raw["species"]
        ]
        self.genera: dict[str, dict] = genera_raw["genera"]
        self._by_name = {s.name.lower(): s for s in self.species}
        self._by_codex = {s.codex_species: s for s in self.species}
        self._by_genus: dict[str, list[Species]] = {}
        for s in self.species:
            self._by_genus.setdefault(s.genus, []).append(s)
        self._alias_to_genus: dict[str, str] = {}
        for genus, meta in self.genera.items():
            self._alias_to_genus[genus.lower()] = genus
            for alias in meta.get("aliases", []):
                self._alias_to_genus[alias.lower()] = genus
            key = meta.get("journal_key", "")
            if key:
                self._alias_to_genus[key.lower()] = genus

    def display_genus(self, name: str | None) -> str:
        """In-game genus label for the active HUD language."""
        from .i18n import game_name
        if not name:
            return ""
        canon = self.resolve_genus(name) or name
        return game_name("genus", canon)

    def display_species(self, name: str | None) -> str:
        from .i18n import game_name
        if not name:
            return ""
        canon_genus = self.resolve_genus(name.split()[0] if name else "") 
        shown_genus = game_name("genus", canon_genus) if canon_genus else None
        if shown_genus and canon_genus and canon_genus != shown_genus:
            return name.replace(canon_genus, shown_genus)
        # Tussock / Touradon either way
        tussock_shown = game_name("genus", "Tussock")
        return name.replace("Tussock", tussock_shown).replace("Touradon", tussock_shown)

    def canonical_genus(self, name: str | None) -> str:
        if not name:
            return ""
        return self.resolve_genus(name) or name

    def resolve_genus(self, name: str | None) -> str | None:
        if not name:
            return None
        return self._alias_to_genus.get(name.strip().lower())

    def species_for_genus(self, genus: str) -> list[Species]:
        canon = self.resolve_genus(genus) or genus
        return list(self._by_genus.get(canon, []))

    def get(self, name: str) -> Species | None:
        return self._by_name.get(name.lower())

    def by_codex(self, key: str) -> Species | None:
        return self._by_codex.get(key)

    @cached_property
    def sorted_by_value(self) -> list[Species]:
        return list(self.species)
