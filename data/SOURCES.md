# Sources de la base exobiologique

Les prix et conditions ne sont pas officiels Frontier. Ils viennent de bases communautaires.

## Prix Vista Genomics

- [Canonn — Vista Genomics Price List](https://canonn.science/codex/vista-genomics-price-list/) (référence principale)
- Contrôle croisé : EDMC-BioScan `bio_data/rulesets/*.py`

Le bonus First Logged / First Footfall est **×5** (valeur de base + 400 %).

Exception connue : BioScan donne 16 777 215 Cr pour Concha Biconcavis ; Canonn donne 19 010 800 Cr. Canonn est retenu.

## Conditions d’apparition

- [SrvSurvey bio-criteria](https://github.com/njthomson/SrvSurvey/tree/main/SrvSurvey/bio-criteria) (juillet 2026)
- Construites à partir de millions d’observations Spansh / Canonn
- Ce sont des **plages empiriques**, pas des règles officielles du jeu
- Deux planètes identiques en type / atmosphère / température n’ont pas forcément la même espèce

Les clauses `regions`, `nebulae` et `star` sont des contraintes supplémentaires. Si elles ne sont pas connues pour le système en cours, l’espèce reste **plausible**, jamais **certaine**.

## Distances d’échantillonnage

Genre uniquement (pas l’espèce) :

- SrvSurvey `BioGenus.getRange`
- EDMC-ExploData `genus.py`

## Documentation journal

- [Elite Dangerous Player Journal — Exploration](https://elite-journal.readthedocs.io/en/latest/Exploration.html)
- [New in Odyssey](https://elite-journal.readthedocs.io/en/latest/New%20in%20Odyssey.html)

Événements utilisés : `Scan`, `FSSBodySignals`, `SAAScanComplete`, `SAASignalsFound`, `ScanOrganic`, `CodexEntry`, `Location`, `FSDJump`.
