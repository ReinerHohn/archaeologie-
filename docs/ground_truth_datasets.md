# Ground-Truth-Datensätze & Schlüsselliteratur (per `literature_mine.py` gefunden)

Das fehlende Puzzleteil war **gelabelte Wahrheit**, um den Detektor *messbar* zu
kalibrieren statt Schwellen zu schätzen. Die Literatur-Recherche (OpenAlex) fand
mehrere **offene, gelabelte Datensätze** – v. a. zu *Relict Charcoal Hearths*
(RCH) in Pennsylvania/USA. Geografie ≠ Schwarzwald, aber die **Label-Polygone +
Methode (Mask R-CNN)** sind direkt zum Trainieren/Validieren nutzbar.

## Offene gelabelte Datensätze (Meiler/Charcoal Hearths)
- **RCH Detection with Mask R-CNN – Polygone** (2021) · doi:10.5281/zenodo.4580726
  — Trainings-/Validierungs-Polygone kartierter Meilerplätze.
- **RCH Detection with Mask R-CNN – Bilder** (2021) · doi:10.5281/zenodo.4583945
  — zugehörige LiDAR-Bildkacheln.
- **Final Product: Mask R-CNN prediction of RCH, SGL PA** (2021) · doi:10.5281/zenodo.4593766
- **False Negatives, Charcoal Hearths SGL 43** (2021) · doi:10.5281/zenodo.4758646
  — wichtig fürs ehrliche Recall-Maß.
- **Methods for Identifying Charcoal Hearths, Blue Mountain** (2018) · doi:10.5281/zenodo.1255101
- **Automated mound detection using LiDAR + OBIA** (2018) · https://orb.binghamton.edu/anthro_data/3
- **Data for „Identifying Landscape Modification Using Open Data and Tools"** (2019) · doi:10.5334/joad.53

## Schlüssel-Methodenliteratur
- **LiDAR Applications in Archaeology: A Systematic Review** (2024) — Überblick/State of the Art.
- Mehrere Mask-R-CNN-/Deep-Learning-Ansätze zur Meiler-Erkennung (2021) mit Open-Access-PDF.

## Wie das unser Projekt voranbringt
1. **Validieren:** unseren `lidar_prospect`/`earthwork_detect` gegen die RCH-Polygone
   laufen lassen → echte Precision/Recall statt Schätzung (schließt die in
   `[[validieren-out-of-sample]]`-Logik beschriebene Lücke).
2. **Schwellen lernen:** `--h-pos`, `--bench-margin`, `--amp-max` an gelabelten
   Beispielen optimieren statt raten.
3. **Perspektive:** Der Feldstandard ist **Mask R-CNN auf Hillshade/LRM-Kacheln** —
   der natürliche nächste Ausbau über die heuristischen Detektoren hinaus.

*Reproduzieren:* `python3 literature_mine.py "charcoal hearths LiDAR" --datasets`
bzw. `python3 literature_mine.py "LiDAR charcoal hearth detection deep learning"`.
