#!/usr/bin/env python3
"""Test: earthwork_detect findet eine synthetische rechteckige Umwallung.

Aufruf:  python3 test_earthwork.py   ->  Exitcode 0 = grün
"""
import sys
import numpy as np

import lidar_prospect as lp
import earthwork_detect as ew

failed = []


def check(name, cond):
    print(("ok  " if cond else "FAIL") + "  " + name)
    if not cond:
        failed.append(name)


# Synthetische Kachel: flacher Hang + rechteckiger Wall (Umwallung) 40x30 m
n = 300
yy, xx = np.mgrid[0:n, 0:n].astype(float)
dem = 200 + 0.02 * xx + 0.3 * np.sin(xx / 40.0)          # sanftes Gelände
# Wall: Rand eines Rechtecks 120..160 (x) / 120..150 (y), ~0.6 m hoch, 2 m breit
wall = np.zeros((n, n))
# realistische Wallbreite ~4 m (echte Ramparts sind 3-8 m breit)
for (r0, r1, c0, c1) in [(120, 124, 120, 160), (146, 150, 120, 160),
                         (120, 150, 120, 124), (120, 150, 156, 160)]:
    wall[r0:r1, c0:c1] = 0.6
dem += wall
tile = lp.Tile(dem, 1.0, 400000.0, 5300000.0, "EPSG:25832")

segs, rings, mask = ew.detect_earthworks(tile, thr=0.15, min_len_m=8.0)
check("Rechteck als Wall-Segmente ODER Ring erkannt", len(segs) >= 3 or len(rings) >= 1)

# Umwallung: entweder über Segment-Cluster oder als Ring-Umriss
encl = ew.cluster_enclosures(segs, radius_m=60.0, min_segs=3, min_orient_bins=2)
found = encl + [{"cx": r["cx"], "cy": r["cy"]} for r in rings]
check("mindestens eine Umwallung erkannt", len(found) >= 1)
if found:
    e = found[0]
    near = abs(e["cx"] - 400140) < 45 and abs(e["cy"] - 5299865) < 45
    check("Umwallung sitzt am Rechteck", near)

# Negativ: glatter Hang ohne Wall -> keine Umwallung
flat = 200 + 0.02 * xx
tile2 = lp.Tile(flat, 1.0, 400000.0, 5300000.0, "EPSG:25832")
segs2, rings2, _ = ew.detect_earthworks(tile2, thr=0.15, min_len_m=8.0)
check("glatter Hang: keine/kaum Erdwerke", len(segs2) + len(rings2) <= 2)

print()
if failed:
    print(f"{len(failed)} Test(s) FEHLGESCHLAGEN: {failed}")
    sys.exit(1)
print("Alle Tests grün.")
