#!/usr/bin/env python3
"""Tests fuer lidar_prospect: Detektor muss die synthetischen Ziele finden.

Aufruf:  python3 test_lidar_prospect.py   ->  Exitcode 0 = alle gruen
"""
import sys

import numpy as np

import lidar_prospect as lp

failed = []


def check(name, cond):
    print(("ok  " if cond else "FAIL") + "  " + name)
    if not cond:
        failed.append(name)


# --- numpy-Filter stimmen mit der Referenz ueberein --------------------------
a = np.arange(25, dtype=float).reshape(5, 5)
bm = lp.box_mean(a, 1)
# Zentrum: Mittel des 3x3-Blocks um (2,2) = Mittel 6,7,8,11,12,13,16,17,18 = 12
check("box_mean Zentrum korrekt", abs(bm[2, 2] - 12.0) < 1e-9)
check("max_filter = echtes Fenstermax",
      lp.max_filter(a, 1)[2, 2] == a[1:4, 1:4].max())

# --- Detektion auf synthetischer Kachel --------------------------------------
tile, truth = lp.make_demo_tile()
hits, lrm = lp.detect(tile)
check("mindestens 4 der 5 Ziele gefunden", len(hits) >= 4)

# jeder gefundene Treffer sitzt nahe an einem echten Ziel (< 4 m)
matched = 0
for cx, cy, kind in truth:
    near = any((h["col"] - cx) ** 2 + (h["row"] - cy) ** 2 <= 4 ** 2 and h["type"] == kind
               for h in hits)
    matched += near
check(">=4 echte Ziele mit korrektem Typ getroffen", matched >= 4)

# keine groben Fehlalarme (Detektor bleibt sparsam auf sauberem Hang)
check("keine Kandidatenflut (<15 Treffer)", len(hits) < 15)

# Radius der Meiler plausibel (2..10 m)
check("Radien im erwarteten Bereich",
      all(2.0 <= h["radius_m"] <= 10.0 for h in hits))

# --- Georeferenz: (row,col)->(x,y) konsistent --------------------------------
x, y = tile.xy(0, 0)
check("xy(0,0) ~ Nordwest-Ecke + halbe Zelle",
      abs(x - (tile.x0 + tile.res / 2)) < 1e-6 and abs(y - (tile.y_top - tile.res / 2)) < 1e-6)

print()
if failed:
    print(f"{len(failed)} Test(s) FEHLGESCHLAGEN: {failed}")
    sys.exit(1)
print("Alle Tests gruen.")
