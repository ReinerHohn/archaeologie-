# 🏺 Archäologie – Methoden für neue Funde

Ein durchsuchbarer **Katalog von Methoden, mit denen man neue archäologische
Fundstellen entdeckt** – zerstörungsfrei, datengetrieben, oft vom Schreibtisch aus.
Sortiert nach **Wirkung ÷ Aufwand**, damit die größten Hebel zuerst kommen.

Die Leitfragen des Projekts:

- **Den Boden durchleuchten** statt blind zu graben – mit Stromfeldern (Geoelektrik),
  Magnetik und Radar „hört“ man ins Erdreich hinein.
- **Aus Luft und All scannen** – LiDAR unter dem Wald, Satellit über ganze Regionen,
  Bewuchsmerkmale im Getreide.
- **Alte Texte und Karten mit KI durchsuchen** – Handschriften lesen, Ortsnamen
  extrahieren, Inschriften datieren, historische Karten punktgenau verorten.
- **Labor & Modellierung** – Datierung, DNA, Isotope, und Wahrscheinlichkeitskarten,
  die verraten, *wo* sich Suchen lohnt.

## Nutzung

```bash
python3 build.py        # baut dashboard.html (self-contained, keine Abhängigkeiten)
python3 test_build.py   # Tests (stdlib, Exitcode 0 = grün)
```

Dann `dashboard.html` im Browser öffnen. Suche + Kategorie-Filter + Sortierung
(Wirkung÷Aufwand · nur Wirkung · geringster Aufwand · Evidenz) sind eingebaut.

## Aufbau (Baumuster)

- `methoden/*.json` – eine Karte je Methode (Datenquelle der Wahrheit).
- `build.py` – reine Python-Standardbibliothek, bündelt alle Karten in **eine**
  HTML-Datei (Daten + CSS + JS eingebettet).
- `dashboard.html` – gebautes Ergebnis (kann direkt geöffnet/committet werden).

### Eine Methode hinzufügen

Neue Datei `methoden/<id>.json`:

```json
{
  "id": "kurzname",
  "title": "Anzeigename",
  "category": "geophysik | fernerkundung | ki_texte | labor | modellierung",
  "impact": 4,
  "effort": 2,
  "evidence_level": "A",
  "what": "Was die Methode ist – ein, zwei Sätze.",
  "how_new_finds": "Warum/wie sie zu NEUEN Funden führt.",
  "how_to": ["Schritt 1", "Schritt 2"],
  "examples": ["Bekannter Fund 1", "Bekannter Fund 2"],
  "combos": ["Andere Methode", "Noch eine"],
  "limits": "Grenzen, Risiken, rechtliche Hinweise.",
  "cost": "Kosten / Zugang."
}
```

Pflichtfelder: `id, title, category, impact, effort, evidence_level, what`.
`impact`/`effort` sind grobe 1–5-Einschätzungen zur Priorisierung.
`evidence_level`: **A** belegt/etabliert · **B** vielversprechend · **C** explorativ.
Danach `python3 build.py` neu ausführen.

## 🎯 Sweet Spot & Werkzeug: `lidar_prospect.py`

Der stärkste Ansatzpunkt für eine Einzelperson mit Code/KI: **offene DGM1-Daten
(1 m LiDAR-Geländemodell) durchkämmen.** Baden-Württemberg gibt DGM1 **kostenlos**
ab – über das Open GeoData Portal <https://opengeodata.lgl-bw.de/> in Kacheln
2 × 2 km (GeoTIFF / ASCII-XYZ / LAZ, Datenlizenz Deutschland). Die rohen
Punktwolken kosten ~80 €/km² – **die brauchst du nicht**, das fertige DGM1-Raster
genügt und ist gratis. Der dicht bewaldete **Schwarzwald** ist damit flächig kaum
katalogisiert: Köhlerei-Meilerplätze, Bergbau-Pingen, Hohlwege und Wüstungen
liegen dort zu Zehntausenden.

`lidar_prospect.py` ist der erste Pipeline-Schritt: es liest DGM1-Kacheln, rechnet
**Hillshade + Local-Relief-Model** und meldet **runde Erhebungen (Meiler)** und
**Vertiefungen (Pingen)** als Punktliste.

```bash
python3 lidar_prospect.py --demo            # synthetische Kachel, sofort testbar
python3 lidar_prospect.py --demo --png      # zusätzlich Hillshade-PNG mit Markern
python3 lidar_prospect.py kachel_dgm1.tif   # echte GeoTIFF-Kachel vom LGL
python3 lidar_prospect.py *.xyz --png       # XYZ-Kacheln, Bildausgabe
python3 test_lidar_prospect.py              # Tests (findet die synthetischen Ziele)
```

Ausgabe je Kachel: `<name>_kandidaten.geojson` + `.csv` (Koordinaten in EPSG:25832
/ UTM32, direkt in QGIS ladbar) und optional `<name>_hillshade.png`.
Abhängigkeiten: `numpy` (Pflicht), `rasterio` (für GeoTIFF, optional),
`Pillow` (für PNG, optional). Parameter (`--bg`, `--h-pos`, `--h-neg`, `--r-min`,
`--r-max`, `--min-sep`) sind auf subtiles Waldrelief voreingestellt und tunebar.

**Der Detektor liefert Kandidaten, keine Beweise.** Die vollständige Pipeline:
DGM1 → `lidar_prospect.py` → in QGIS gegen Altkarten/Luftbilder + textgeminte
Wüstungsnamen filtern → mit Drohne/Begehung prüfen → **der Denkmalpflege melden.**

## Hinweis

Wirkung/Aufwand sind Einordnungshilfen, keine harten Messwerte. Und: Feldarbeit,
Metalldetektion und Grabung sind vielerorts **genehmigungspflichtig** – erst die
Rechtslage klären, dann suchen. Fundkontext ist unwiederbringlich; melden statt
selbst bergen.
