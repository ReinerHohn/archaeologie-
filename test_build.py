#!/usr/bin/env python3
"""Minimaltests fuer den Katalog-Build (stdlib, ohne Framework).

Aufruf:  python3 test_build.py   ->  Exitcode 0 = alle gruen
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
import build  # noqa: E402

failed = []


def check(name, cond):
    print(("ok  " if cond else "FAIL") + "  " + name)
    if not cond:
        failed.append(name)


# 1) alle Karten laden ohne sys.exit + Pflichtfelder + gueltige Kategorie
cards = build.load_cards()
check("mindestens 15 Methoden vorhanden", len(cards) >= 15)
check("alle Kategorien gueltig", all(c["category"] in build.CATEGORIES for c in cards))
check("keine doppelten ids", len({c["id"] for c in cards}) == len(cards))
check("impact/effort im Bereich 1..5",
      all(1 <= c["impact"] <= 5 and 1 <= c["effort"] <= 5 for c in cards))
check("evidence_level in A/B/C", all(c["evidence_level"] in "ABC" for c in cards))
check("_score = impact/effort korrekt",
      all(abs(c["_score"] - round(c["impact"] / c["effort"], 2)) < 1e-9 for c in cards))

# 2) Default-Sortierung ist absteigend nach Hebel
scores = [c["_score"] for c in cards]
check("default nach Wirkung/Aufwand sortiert (absteigend)", scores == sorted(scores, reverse=True))

# 3) Kernmethoden aus dem Auftrag sind enthalten
ids = {c["id"] for c in cards}
for must in ("geoelektrik", "lidar", "htr-alte-handschriften", "ner-ortsnamen"):
    check(f"Kernmethode '{must}' vorhanden", must in ids)

# 4) build.py erzeugt valides dashboard.html mit eingebettetem, parsebarem JSON
subprocess.run([sys.executable, str(ROOT / "build.py")], check=True, cwd=ROOT)
htmltext = (ROOT / "dashboard.html").read_text(encoding="utf-8")
m = re.search(r"const CARDS = (\[.*?\]);\nconst CATS", htmltext, re.S)
check("dashboard.html enthaelt CARDS-Array", m is not None)
if m:
    embedded = json.loads(m.group(1))
    check("eingebettetes JSON == Kartenzahl", len(embedded) == len(cards))
    check("jede eingebettete Karte hat Suchindex _hay", all("_hay" in c for c in embedded))

print()
if failed:
    print(f"{len(failed)} Test(s) FEHLGESCHLAGEN: {failed}")
    sys.exit(1)
print("Alle Tests gruen.")
