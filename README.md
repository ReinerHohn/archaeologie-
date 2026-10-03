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

### DGM1 automatisch laden: `fetch_dgm_bw.py`

Lädt die kostenlosen DGM1-Kacheln des LGL direkt (Schema aus dem Portal
zurückentwickelt: `…/data/dgm/dgm1_32_<Ost_km>_<Nord_km>_2_bw.zip`, 2-km-Gitter
mit **ungeraden Ost-km** und **geraden Nord-km**; jede ZIP enthält vier
1-km-XYZ-Dateien, EPSG:25832):

```bash
# per Kachel-Ecken (UTM-km):
python3 fetch_dgm_bw.py --tiles 417,5316 415,5314 --out data/freiburg_ost
# per Umkreis um Koordinaten (lat,lon – braucht rasterio für die Projektion):
python3 fetch_dgm_bw.py --center 47.995,7.852 --radius-km 3 --out data/freiburg
# nur prüfen, welche Kacheln existieren:
python3 fetch_dgm_bw.py --center 47.995,7.852 --radius-km 3 --list-only
```

### Literatur & Wissen durchforsten + Puzzleteile zusammenlegen

Funde entstehen nicht nur aus Relief, sondern aus dem **Zusammenlegen von
Text- und Raumquellen**:

- **`literature_mine.py`** — durchsucht wissenschaftliche Literatur (OpenAlex,
  offen) nach Methoden **und offenen, gelabelten Datensätzen** (Ground Truth zum
  Kalibrieren). Siehe `docs/ground_truth_datasets.md`.
  ```bash
  python3 literature_mine.py "charcoal hearths LiDAR" --datasets
  ```
- **`geo_clues.py`** — holt georeferenziertes Wissen (Wikidata + Wikipedia:
  Burgen, Ruinen, Schanzen, Wüstungen, Klöster …) und **fusioniert es räumlich**
  mit den LiDAR-Kandidaten → „Puzzle-Matches" (Textquelle ↔ Anomalie).
  ```bash
  python3 geo_clues.py --from freiburg_funde.geojson --fuse freiburg_funde.geojson --name freiburg
  ```
  Beispiel-Match im Testlauf: **Burg Kybfelsen ↔ Ring-Erdwerk 134 m daneben.**

### Daten-Fusion: `discovery_score.py` (versteckte Funde aufspüren)

Der eigentliche Hebel für *versteckte* Archäologie ist **Daten-Fusion**: ein
Kandidat ist heiß, wenn mehrere unabhängige Quellen zusammenfallen. Das Werkzeug
fasst sie zu einem Score zusammen und gibt eine **Rangliste** aus:

```
Erdwerk (Umwallung/Ring im LiDAR)
 × im Wald  × nicht an moderner Straße  × NICHT im amtlichen Verzeichnis
 + Bonus bei historischem Hinweis in der Nähe (Flurname „Burgstall/Schanze/
   Ringwall/Wüstung…" oder OSM-historic)
```

```bash
python3 discovery_score.py --data data/freiburg_ost --name freiburg --figures
# -> freiburg_funde.geojson + .csv (nach Score) + docs/..._kontaktbogen.png
```

### Alles in einem: `pipeline.py`

Die ganze Kette (laden → detektieren → Wald/Wege-Filter → amtlicher
Denkmal-Abgleich → Rangliste der *unbekannten* Kandidaten) in einem Kommando:

```bash
python3 pipeline.py --center 47.995,7.852 --radius-km 3 --out data/freiburg
```

Produkte: `fetch_dgm_bw.py --product` kann `dgm1` (1 m XYZ), `dgm025`
(0,25 m GeoTIFF – zum Nachprüfen einzelner Kandidaten), `dom1` und `dop20`
(Luftbild-Orthofoto, zum Unterscheiden „modern vs. alt") laden.

### Echtes Gelände: die zwei Diskriminatoren

Auf realen Schwarzwald-Hängen flutet ein reiner Relief-Detektor (Bachtäler,
Felsen, Hangkanten). Zwei Filter machen ihn brauchbar:

- `--amp-max` (Standard 1,5 m): Meiler/Pingen sind **flach** – metertiefe
  Naturformen fliegen raus.
- `--bench-margin` (Standard 0 = aus; für Wald **~3**): erzwingt die echte
  Meiler-Signatur **„flache Bühne AUF einem Hang"** – die Umgebung muss steiler
  sein als die Platte. Schließt flache Talböden UND gleichmäßige Steilhänge aus.

Beispiel (Wald östlich Freiburg, ~8 km²): ohne Filter >2000 Treffer/km²,
mit `--bench-margin 3 --h-pos 0.2` **~10–50 plausible Kandidaten/km²** –
in der Größenordnung bekannter Meilerplatz-Dichten:

```bash
python3 fetch_dgm_bw.py --tiles 417,5316 415,5314 --out data/freiburg_ost
python3 lidar_prospect.py data/freiburg_ost/*.xyz --bench-margin 3 --h-pos 0.2 --png
```

Ausgabe je Kachel: `<name>_kandidaten.geojson` + `.csv` (Koordinaten in EPSG:25832
/ UTM32, direkt in QGIS ladbar) und optional `<name>_hillshade.png`.
Abhängigkeiten: `numpy` (Pflicht), `rasterio` (für GeoTIFF, optional),
`Pillow` (für PNG, optional). Parameter (`--bg`, `--h-pos`, `--h-neg`, `--r-min`,
`--r-max`, `--min-sep`) sind auf subtiles Waldrelief voreingestellt und tunebar.

### Rechteckige/lineare Erdwerke: `earthwork_detect.py`

`lidar_prospect.py` findet nur RUNDE Formen (Meiler/Pingen). Für **Wälle,
Gräben-Ränder und rechteckige Umwallungen** (z. B. Schanzen/Redouten, Burgställe,
Wasserbecken) gibt es `earthwork_detect.py`: es findet schmale, lange Grate im
Local-Relief-Model (Wall-Segmente) und erkennt dicht stehende, verschieden
orientierte Segmente bzw. hohle Umriss-Komponenten als **Umwallungen**.

```bash
python3 earthwork_detect.py data/freiburg_ost/*.xyz --png
```

Validiert am Rosskopf-Erdwerk: der Detektor zeichnet die rechteckige Doppel-
Umwallung sauber nach (die `lidar_prospect` nur zufällig am Rand streifte).

### Auf Wald filtern: `forest_filter.py` (großer Qualitätshebel)

Meilerplätze liegen im Wald – die meisten Fehlalarme (Feld-, Talboden-,
Siedlungsrelief) nicht. `forest_filter.py` holt kostenlose OSM-Waldpolygone
(Overpass) für die Bounding-Box der Kandidaten und behält nur Punkte im Wald:

```bash
python3 forest_filter.py freiburg_region_kandidaten.geojson
# -> freiburg_region_kandidaten_wald.geojson
```

**Moderne Wege ausschließen (`--exclude-roads-m`, wichtig!):** In den Freiburger
Realdaten lagen **78 % der Wald-Kandidaten ≤ 20 m an einem OSM-Weg** – ein in den
Hang gebauter Forstweg erzeugt eine „flache Bühne am Hang" und imitiert damit die
Meiler-Signatur. Wege ausschließen entfernt diese Haupt-Fehlerquelle:

```bash
python3 forest_filter.py freiburg_region_kandidaten.geojson --exclude-roads-m 20
```

### Ergebnis „Raum Freiburg" (Referenzlauf, 6 Kacheln ≈ 24 km²)

Kappler/Rosskopf/Günterstal/Schauinsland-Fuß, `--bench-margin 3 --h-pos 0.2`:
**515 Rohkandidaten → 185 im Wald → 26 im Wald UND abseits Wege** (>20 m;
15 Meiler-artig, 11 Pingen-artig). Der Wald- plus Wege-Filter siebt also die
klaren Fehlerquellen (Talboden, Siedlung, Forstweg-Anschnitte) aus. Reproduzieren:

```bash
python3 fetch_dgm_bw.py --tiles 417,5316 415,5314 419,5318 419,5320 415,5312 417,5312 --out data/freiburg_ost
python3 lidar_prospect.py data/freiburg_ost/*.xyz --bench-margin 3 --h-pos 0.2
# alle *_kandidaten.geojson zusammenführen, dann:
python3 forest_filter.py <zusammengeführte>.geojson --exclude-roads-m 20
```

Die verbleibenden Kandidaten sind **Hinweise, keine Funde** – erst visuell im
Hillshade prüfen, dann im Gelände, dann der Denkmalpflege melden.

### Gegen das amtliche Denkmalverzeichnis abgleichen: `denkmal_check.py`

„Was davon ist längst bekannt?" – gleicht die Kandidaten gegen den offenen WMS
des **Landesamts für Denkmalpflege BW** ab (archäologische Kulturdenkmale +
Grabungsschutzgebiete, `owsproxy.lgl-bw.de`, EPSG:25832). Markiert je Kandidat
`amtlich_bekannt` und holt bei Treffern den Klartext (GetFeatureInfo):

```bash
python3 denkmal_check.py freiburg_region_kandidaten.geojson --radius-m 25
# -> freiburg_region_kandidaten_denkmalabgleich.geojson
```

Ergebnis im Raum Freiburg: nur **6 % (33/515)** liegen ≤ 25 m an einem
eingetragenen Denkmal – und die verteilen sich auf **wenige Typen** (v. a. die
frühneuzeitliche **Schanzenlinie** Rosskopf–Dreisamtal–Sternwald ~1700,
Kirche+Friedhof, Gewerbekanal, „Wildbad"). Die eingetragenen Denkmale liegen
also fast alle woanders als unsere Waldkandidaten. **Wichtig:** „nicht im
Verzeichnis" heißt NICHT automatisch „neue Entdeckung" – es kann genauso ein
Fehlalarm (Weg-Bank, Naturform) sein. Der Abgleich trennt nur *bekannt* von
*unbekannt*, nicht *echt* von *falsch*.

**Der Detektor liefert Kandidaten, keine Beweise.** Die vollständige Pipeline:
DGM1 → `lidar_prospect.py` → `forest_filter.py` (Wald + Wege) →
`denkmal_check.py` (Bekanntes markieren) → in QGIS gegen Altkarten/Luftbilder +
textgeminte Wüstungsnamen filtern → mit Drohne/Begehung prüfen →
**der Denkmalpflege melden.**

## Hinweis

Wirkung/Aufwand sind Einordnungshilfen, keine harten Messwerte. Und: Feldarbeit,
Metalldetektion und Grabung sind vielerorts **genehmigungspflichtig** – erst die
Rechtslage klären, dann suchen. Fundkontext ist unwiederbringlich; melden statt
selbst bergen.
