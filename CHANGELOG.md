# Changelog

Player-facing notes. Windows builds are on [Releases](https://github.com/jr-hub-dev/ScanDeck/releases). When tagging a version, paste the matching section into the GitHub Release (keep the unzip / SmartScreen line).

## 1.0.2 — 2026-09-08

### Added
- Version in the HUD footer (`v1.0.2`)
- If a newer GitHub release exists, **UPDATE** / **MAJ** appears next to it — click to open the download page

## 1.0.1 — 2026-09-08

### Fixed
- Windows `ScanDeck.exe` crashed on launch (`attempted relative import with no known parent package`)

## 1.0.0 — 2026-09-08

First public release.

### Added
- HUD: system bodies after FSS, genera after DSS, species hints, land / skip verdict
- Genetic Sampler progress, Nomad IDs, unsold cartography & Vista Genomics, explorer / exobiologist rank rails
- Optional spreadsheet of DSS samples
- Options: language (English, French, Spanish) and journal folder
- Windows zip (no Python) and run-from-source (`python3 -m scandeck`)
