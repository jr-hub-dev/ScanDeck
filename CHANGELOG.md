**English** · [Français](CHANGELOG.fr.md) · [Español](CHANGELOG.es.md)

# Changelog

What changed for players. Windows zips: [Releases](https://github.com/jr-hub-dev/ScanDeck/releases).

The GitHub “Full Changelog” compare link is a **code diff**, not these notes.

## 1.0.6 — 2026-09-12

### Added
- Notable stellar phenomena: cyan banner in the left list after the honk; Codex name after you scan them
- Spreadsheet **explo** sheet: Earth-like worlds, water worlds, ammonia worlds, and stellar phenomena (one row per find)
- UC / Vista to sell show **base** and **First logged** on one line, plus an **FC** line (what you keep after crew + fleet carrier tax)

### Changed
- Hold amounts use **Md** / **Bn** from one billion; each amount turns green on its own when it covers the next rank

## 1.0.5 — 2026-09-09

### Fixed
- Selling Universal Cartographics now updates the explorer rank remaining (it used to stay on the last journal Progress %)

## 1.0.4 — 2026-09-08

### Changed
- Unsold lines are labeled **UC TO SELL** (cartography, left) and **VISTA TO SELL** (biology, right)

## 1.0.3 — 2026-09-08

### Added
- App icon (cyan planet / scan rings) in the HUD, taskbar, and Windows `ScanDeck.exe`

### Fixed
- Crash on launch with Python 3.14 (`wm_class`)

## 1.0.2 — 2026-09-08

### Added
- Version number in the HUD footer
- If a newer release exists on GitHub, **UPDATE** appears beside it — click to open the download page

## 1.0.1 — 2026-09-08

### Fixed
- Windows `ScanDeck.exe` crashed immediately on launch

## 1.0.0 — 2026-09-08

First public release.

### Added
- HUD: bodies after FSS, bio families (genera) after DSS, species hints, land / skip verdict
- Genetic Sampler progress, Nomad IDs, unsold cartography & Vista Genomics, explorer / exobiologist rank rails
- Optional spreadsheet of DSS samples
- Options: language (English, French, Spanish) and journal folder
- Windows zip (no Python) and run-from-source
