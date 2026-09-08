[English](README.md) · **Français** · [Español](README.es.md) · [Versions](CHANGELOG.fr.md)

# ScanDeck

HUD d’exploration et d’exobiologie pour **Elite Dangerous Odyssey**.

Il lit les journaux du jeu en temps réel et reste au-dessus du bureau. Après le honk et les scans, il liste les corps, les espèces possibles, les données Universal Cartographics / Vista Genomics pas encore vendues, et la progression des rangs explorateur / exobiologiste.

Le HUD existe aujourd’hui en **anglais, français et espagnol**. Les noms du jeu (familles de bios, types de planètes, rangs) suivent le client Elite quand c’est possible. La plupart des familles Odyssey restent en latin ; l’exception française connue est **Tussock → Touradon**.

C’est un overlay compagnon, pas un mod. Il ne s’injecte pas dans le jeu.

Journal des versions : [Français](CHANGELOG.fr.md) · [English](CHANGELOG.md) · [Español](CHANGELOG.es.md) · [Releases](https://github.com/jr-hub-dev/ScanDeck/releases)

## Prérequis

- Elite Dangerous **Odyssey**
- Journaux activés (défaut Windows : `%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous`)
- **Zip Windows :** rien d’autre
- **Depuis les sources :** Python 3.11+ avec Tk. `openpyxl` est optionnel (classeur)

## Installation

### Windows (recommandé)

1. Télécharge **ScanDeck-windows.zip** dans les [Releases](https://github.com/jr-hub-dev/ScanDeck/releases).
2. Dézippe **tout** le dossier quelque part (Bureau, Documents, …).
3. Lance `ScanDeck.exe` **depuis ce dossier**. Ne sors pas l’exe tout seul.
4. Si SmartScreen s’affiche : **Plus d’infos → Exécuter quand même**.

Démarre ScanDeck **avant ou pendant** la partie. Au lancement il rejoue les journaux récents, puis suit le log en direct.

### Linux / macOS / Windows avec Python

```bash
git clone https://github.com/jr-hub-dev/ScanDeck.git
cd ScanDeck
pip install -r requirements.txt
python3 -m scandeck
```

Sous Windows avec Python : `python -m scandeck`. Sous Linux tu peux aussi lancer `./scandeck.sh`.

```text
python3 -m scandeck --lang auto   # défaut : OS, puis client Elite
python3 -m scandeck --lang en
python3 -m scandeck --lang fr
python3 -m scandeck --lang es
```

## Premier lancement

Si le HUD ne trouve pas les journaux, clique **Options** (en bas à gauche) :

- **Langue** — Auto / English / Français / Español. D’autres langues de l’interface pourront être ajoutées plus tard ; la liste dans Options s’allongera.
- **Dossier des journaux** — laisse vide pour la détection auto, ou Parcourir jusqu’au dossier qui contient les `Journal.*.log`

Emplacements habituels :

| Plateforme | Dossier |
|---|---|
| Windows | `Saved Games\Frontier Developments\Elite Dangerous` dans ton profil utilisateur |
| Steam / Proton | `~/.steam/steam/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous` |
| Wine / Heroic | dans le préfixe, le même chemin `Saved Games\Frontier Developments\Elite Dangerous` |

Les réglages sont dans `Documents\ScanDeck\config.json` (Windows) ou `~/.local/share/ScanDeck/config.json` (Linux). Changer la langue ou les journaux relance le HUD.

`--journal-dir` et `ED_JOURNAL_DIR` passent avant Options.

## Fonctionnement

Joue normalement. ScanDeck ne fait qu’écouter les journaux.

En exobiologie Odyssey, un **genre** (en anglais *genus*, pluriel *genera*) est la **famille** du bio — Bacterium, Stratum, Touradon, etc. Ce n’est pas « général ». L’**espèce** est l’organisme précis (par exemple Bacterium Aurasus). Il n’y a qu’une espèce par genre sur une planète donnée.

1. **Honk (scan de découverte FSS)** — les corps apparaissent **à gauche**. Les signaux bio ne sont pas sur le honk ; scanne chaque planète dans le FSS.
2. **FSS d’une planète** — type, signaux, une première estimation de valeur. Pastilles : **carto** si déjà cartographiée, **FF** si déjà footfall.
3. **DSS (cartographie détaillée)** — révèle ces **genres** (les familles), pas l’espèce exacte. Le panneau **de droite** liste les espèces compatibles et un verdict atterrir / passer.
4. **Atterrir** — Genetic Sampler : Log → Sample → Analyse (1/3, 2/3, terminé). Le Codex / Nomad peut identifier une espèce avant l’échantillon.
5. **Vendre** — Universal Cartographics et Vista Genomics. **UC À VENDRE** (gauche) = cartographie non vendue ; **VISTA À VENDRE** (droite) = bios non vendues. Elles se vident à la vente. Elles passent au vert quand la soute couvre le reste jusqu’au rang suivant.

### Disposition du HUD

| Zone | Contenu |
|---|---|
| Liste gauche | Corps du système en cours |
| Panneau droit | Planète sélectionnée : verdict, genres, espèces, progression des scans |
| Frise tout à gauche | Rang explorateur |
| Frise tout à droite | Rang exobiologiste |
| Pied de fenêtre | **Ouvrir le classeur**, **Options**, version (`v1.0.3`). S’il existe une Release GitHub plus récente, **MAJ v…** s’affiche — un clic ouvre la page de téléchargement. |

Clique un corps à gauche pour l’ouvrir à droite. Les boutons de copie à côté du système / du corps copient ce nom.

Les verdicts sont une indication d’atterrissage (haute valeur, optionnel, passer), pas une garantie que l’espèce est là.

### Classeur

**Ouvrir le classeur** écrit `scandeck.xlsx` à côté de la config (Documents / ScanDeck sous Windows). Une ligne par planète × genre DSS, mise à jour au fur et à mesure des échantillons. Il faut `openpyxl` (inclus dans le zip Windows).

## Ce que ScanDeck ne sait pas

- Une planète compatible n’implique **pas** que l’espèce y soit.
- Le DSS confirme le **genre** (la famille), pas l’espèce, tant que le sampler ou le Nomad n’a pas parlé.
- `ScanOrganic Log` est une identification, pas un échantillon terminé.
- Les conditions d’apparition viennent de [SrvSurvey](https://github.com/njthomson/SrvSurvey) / [Canonn](https://canonn.science/codex/vista-genomics-price-list/) (observations), pas de Frontier. Détails : [`data/SOURCES.md`](data/SOURCES.md).
- Les valeurs de scan suivent des tables communautaires (cartographie style MattG / EDDI ; prix Vista Canonn). Bonus First Logged / First Footfall bio : ×5.
