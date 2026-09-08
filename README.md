# ScanDeck

Exploration & exobiology HUD for **Elite Dangerous Odyssey**.

Reads the game journals. After FSS/DSS it lists bodies, predicted species, unsold Universal Cartographics / Vista Genomics data, and rank rails.

Languages: **English, French, Spanish**. UI strings are translated; in-game names (genera, planet types, ranks) follow the game client when possible (`Fileheader.language`, journal `*_Localised`). Most Odyssey genera stay Latin; French **Tussock → Touradon** is the known exception.

## Windows (no Python)

Download **ScanDeck-windows.zip** from [Releases](https://github.com/jr-hub-dev/ScanDeck/releases). Unzip and run `ScanDeck.exe`. Keep the whole folder together — do not move the exe out on its own.

Windows SmartScreen may warn on the first launch: **More info → Run anyway**.

## Install from source

Python 3.11+ with Tk.

```bash
git clone https://github.com/jr-hub-dev/ScanDeck.git
cd ScanDeck
pip install -r requirements.txt
python3 -m scandeck
```

On Windows with Python: `python -m scandeck`. Linux: `./scandeck.sh` or `python3 -m scandeck`.

`--lang auto|en|fr|es` — `auto` (default) follows the OS, then the Elite client language from the journal.

## Journals

Detected on Windows (`Saved Games/Frontier Developments/Elite Dangerous`) and Linux (Proton / Wine / Heroic). Override with **Options** in the HUD, `--journal-dir`, or `ED_JOURNAL_DIR`. Language and journal folder are saved in the ScanDeck data folder (`config.json`).

The workbook is stored in `Documents/ScanDeck/` (Windows) or `~/.local/share/ScanDeck/` (Linux), not next to the game. `openpyxl` is optional; without it the HUD still runs, without the spreadsheet.

## Notes

- A compatible planet does **not** guarantee a species.
- DSS gives **genera**, not the exact species, until the Genetic Sampler speaks.
- Criteria come from SrvSurvey / Canonn (observations, not official rules).

Russian is not included yet.
