**English** · [Français](README.fr.md) · [Español](README.es.md)

# ScanDeck

Exploration and exobiology HUD for **Elite Dangerous Odyssey**.

It reads the game journals in real time and sits on top of the desktop. After you honk and scan, it lists bodies, predicted species, unsold Universal Cartographics / Vista Genomics data, and explorer / exobiologist rank progress.

The HUD is currently in **English, French, and Spanish**. In-game names (bio families, planet types, ranks) follow the Elite client when possible. Most Odyssey bio families keep their Latin names; the known French exception is **Tussock → Touradon**.

This is a companion overlay, not a game mod. It does not inject into the client.

Changelog: [CHANGELOG.md](CHANGELOG.md) · [Releases](https://github.com/jr-hub-dev/ScanDeck/releases)

## Requirements

- Elite Dangerous **Odyssey**
- Journals enabled (default: `%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous`)
- **Windows zip:** nothing else
- **From source:** Python 3.11+ with Tk. `openpyxl` is optional (spreadsheet)

## Install

### Windows (recommended)

1. Download **ScanDeck-windows.zip** from [Releases](https://github.com/jr-hub-dev/ScanDeck/releases).
2. Unzip the whole folder somewhere (Desktop, Documents, …).
3. Run `ScanDeck.exe` **from that folder**. Do not move the exe out on its own.
4. If SmartScreen appears: **More info → Run anyway**.

Start ScanDeck **before or while** you play. It replays recent journals on launch, then follows the live log.

### Linux / macOS / Windows with Python

```bash
git clone https://github.com/jr-hub-dev/ScanDeck.git
cd ScanDeck
pip install -r requirements.txt
python3 -m scandeck
```

On Windows with Python: `python -m scandeck`. On Linux you can also run `./scandeck.sh`.

```text
python3 -m scandeck --lang auto   # default: OS, then Elite client
python3 -m scandeck --lang en
python3 -m scandeck --lang fr
python3 -m scandeck --lang es
```

## First launch

If the HUD says it cannot find journals, click **Options** (bottom left):

- **Language** — Auto / English / Français / Español. More HUD languages can be added later; the list in Options will grow.
- **Journal folder** — leave empty to auto-detect, or Browse to the folder that contains `Journal.*.log` files

Typical locations:

| Platform | Folder |
|---|---|
| Windows | `Saved Games\Frontier Developments\Elite Dangerous` under your user profile |
| Steam / Proton | `~/.steam/steam/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous` |
| Wine / Heroic | under the prefix, same `Saved Games\Frontier Developments\Elite Dangerous` path |

Settings are saved in `Documents\ScanDeck\config.json` (Windows) or `~/.local/share/ScanDeck/config.json` (Linux). Changing language or journals restarts the HUD.

Command-line `--journal-dir` and `ED_JOURNAL_DIR` override Options.

## How it works

Play normally. ScanDeck only listens to journals.

In Odyssey exobiology, a **genus** (plural **genera**) is the bio *family* — Bacterium, Stratum, Tussock, and so on. A **species** is the exact organism (for example Bacterium Aurasus). There is only one species per genus on a given planet.

1. **Honk (FSS discovery scan)** — bodies appear on the **left**. Bio signals are not on the honk; scan each planet in the FSS.
2. **FSS a planet** — body type, signals, a first value estimate. Tags: **carto** if already mapped, **FF** if already footfalled.
3. **DSS (detailed surface scan)** — reveals those **genera** (the families), not the exact species. The **right** pane lists matching species and a land / skip verdict.
4. **Land** — Genetic Sampler: Log → Sample → Analyse (1/3, 2/3, done). Codex / Nomad can identify a species before you sample it.
5. **Sell** — Universal Cartographics and Vista Genomics. The **TO SELL** lines track unsold scans (cartography left, biology right). They clear when you sell. They turn green when the hold covers the remaining credits to the next rank.

### HUD layout

| Area | What you see |
|---|---|
| Left list | Bodies in the current system |
| Right pane | Selected planet: verdict, genera, species, scan progress |
| Far left rail | Explorer rank |
| Far right rail | Exobiologist rank |
| Footer | **Open spreadsheet**, **Options**, version (`v1.0.2`). If a newer GitHub release exists, **UPDATE v…** appears — click it to open the release page. |

Click a body on the left to open it on the right. Copy buttons next to the system / body name copy that name.

Verdicts are a landing hint (high value, optional, skip), not a guarantee the species is there.

### Spreadsheet

**Open spreadsheet** writes `scandeck.xlsx` next to the config (Documents / ScanDeck on Windows). One row per planet × DSS genus, updated as you sample. Needs `openpyxl` (included in the Windows zip).

## What ScanDeck does *not* know

- A planet matching the criteria does **not** guarantee that species.
- DSS confirms the **genus** (family), not the species, until the sampler or Nomad speaks.
- `ScanOrganic Log` is an identification, not a completed sample.
- Appearance rules come from [SrvSurvey](https://github.com/njthomson/SrvSurvey) / [Canonn](https://canonn.science/codex/vista-genomics-price-list/) observations, not Frontier. Details: [`data/SOURCES.md`](data/SOURCES.md).
- Scan values follow community tables (MattG / EDDI-style cartography; Canonn Vista prices). First Logged / First Footfall bio bonus is ×5.
