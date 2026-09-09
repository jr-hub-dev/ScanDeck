[English](CHANGELOG.md) · **Français** · [Español](CHANGELOG.es.md)

# Journal des versions

Ce qui a changé pour les joueurs. Zips Windows : [Releases](https://github.com/jr-hub-dev/ScanDeck/releases).

Le lien GitHub « Full Changelog » est un **diff de code**, pas ces notes.

## 1.0.5 — 2026-09-09

### Corrigé
- Vendre à Universal Cartographics met à jour le reste jusqu’au prochain rang explorateur (il restait calé sur le dernier % journal)

## 1.0.4 — 2026-09-08

### Modifié
- Les lignes non vendues s’appellent **UC À VENDRE** (cartographie, gauche) et **VISTA À VENDRE** (bio, droite)

## 1.0.3 — 2026-09-08

### Ajouté
- Icône de l’app (planète cyan / anneaux de scan) dans le HUD, la barre des tâches et `ScanDeck.exe` sous Windows

### Corrigé
- Plantage au lancement avec Python 3.14 (`wm_class`)

## 1.0.2 — 2026-09-08

### Ajouté
- Numéro de version en bas du HUD
- S’il existe une Release plus récente, **MAJ** s’affiche à côté — un clic ouvre la page de téléchargement

## 1.0.1 — 2026-09-08

### Corrigé
- `ScanDeck.exe` (Windows) plantait tout de suite au lancement

## 1.0.0 — 2026-09-08

Première version publique.

### Ajouté
- HUD : corps après le FSS, genres (familles de bios) après le DSS, espèces possibles, verdict atterrir / passer
- Progression Genetic Sampler, identifications Nomad, cartographie et Vista Genomics non vendues, frises de rang explorateur / exobiologiste
- Classeur optionnel des échantillons DSS
- Options : langue (anglais, français, espagnol) et dossier des journaux
- Zip Windows (sans Python) et lancement depuis les sources
