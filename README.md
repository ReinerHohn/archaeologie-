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

## Hinweis

Wirkung/Aufwand sind Einordnungshilfen, keine harten Messwerte. Und: Feldarbeit,
Metalldetektion und Grabung sind vielerorts **genehmigungspflichtig** – erst die
Rechtslage klären, dann suchen. Fundkontext ist unwiederbringlich; melden statt
selbst bergen.
