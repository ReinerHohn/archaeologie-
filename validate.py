#!/usr/bin/env python3
"""Validierungs-Harnisch: Precision/Recall/F1 + Schwellen-Sweep gegen Ground Truth.

Macht aus geschätzten Detektor-Schwellen GELERNTE: man gibt ein DGM mit
gelabelten Fundstellen (GeoJSON-Punkte oder -Polygone), das Werkzeug fährt einen
Parameter-Sweep (--h-pos, --bench-margin) und meldet je Kombination
Precision/Recall/F1 + die beste Einstellung.

Modi:
  # reine Metrik: Kandidaten vs. Wahrheit
  python3 validate.py --candidates funde.geojson --truth wahrheit.geojson --max-m 15
  # Sweep über ein gelabeltes DGM (lernt die beste Schwelle)
  python3 validate.py --dem kachel.xyz --truth wahrheit.geojson
  # Selbsttest auf realistischer synthetischer Szene (bekannte Meiler + Störer)
  python3 validate.py --demo

Wahrheit: GeoJSON FeatureCollection; Point-Geometrie direkt, Polygon -> Zentroid.
Alles EPSG:25832 (bzw. gleiches CRS wie Kandidaten).
"""
import argparse
import json
import pathlib
import sys

import numpy as np

import lidar_prospect as lp


def load_points(path):
    d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    pts = []
    for f in d["features"]:
        g = f["geometry"]
        if g["type"] == "Point":
            pts.append(tuple(g["coordinates"][:2]))
        elif g["type"] in ("Polygon", "MultiPolygon"):
            coords = g["coordinates"]
            ring = coords[0] if g["type"] == "Polygon" else coords[0][0]
            arr = np.array(ring)[:, :2]
            pts.append((float(arr[:, 0].mean()), float(arr[:, 1].mean())))
    return pts


def match(cand_xy, truth_xy, max_m):
    """Greedy nächster-Nachbar-Match. Liefert TP, FP, FN + Metriken."""
    cand = list(cand_xy)
    pairs = []
    for ti, (tx, ty) in enumerate(truth_xy):
        pairs += [(np.hypot(cx - tx, cy - ty), ti, ci) for ci, (cx, cy) in enumerate(cand)]
    pairs.sort()
    used_t, used_c = set(), set()
    tp = 0
    for d, ti, ci in pairs:
        if d > max_m:
            break
        if ti in used_t or ci in used_c:
            continue
        used_t.add(ti); used_c.add(ci); tp += 1
    fp = len(cand) - tp
    fn = len(truth_xy) - tp
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(prec, 3),
            "recall": round(rec, 3), "f1": round(f1, 3)}


def detect_xy(tile, h_pos, bench):
    hits, _ = lp.detect(tile, h_pos=h_pos, h_neg=h_pos, bench_margin=bench)
    return [(h["x"], h["y"]) for h in hits if h["type"] == "meiler"]


def sweep(tile, truth_xy, max_m, h_list, bench_list):
    print(f"\nSchwellen-Sweep (max_m={max_m}):")
    print(f"{'h_pos':>6} {'bench':>6} {'P':>6} {'R':>6} {'F1':>6}  TP/FP/FN")
    best = None
    for b in bench_list:
        for h in h_list:
            cand = detect_xy(tile, h, b)
            m = match(cand, truth_xy, max_m)
            print(f"{h:6.2f} {b:6.1f} {m['precision']:6.3f} {m['recall']:6.3f} "
                  f"{m['f1']:6.3f}  {m['tp']}/{m['fp']}/{m['fn']}")
            if best is None or m["f1"] > best[0]:
                best = (m["f1"], h, b, m)
    f1, h, b, m = best
    print(f"\nBESTE: --h-pos {h} --bench-margin {b}  -> F1 {f1} "
          f"(P {m['precision']}, R {m['recall']})")
    return best


def make_labeled_demo(n=600, res=1.0, seed=7):
    """Realistische Szene: Hang + korreliertes Rauschen + 12 Meiler + Störer + Weg."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:n, 0:n].astype(float)
    dem = 300 + 0.06 * xx + 0.02 * yy                        # Hang
    # korreliertes Mikro-Rauschen (geglättetes Weißrauschen)
    nz = rng.standard_normal((n, n))
    dem += 0.15 * lp.box_mean(nz, 3)
    truth = []

    def disc(cx, cy, r, amp):
        return amp * np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (r ** 2))))

    rng2 = np.random.default_rng(seed + 1)
    for _ in range(12):                                      # echte Meiler
        cx, cy = rng2.integers(60, n - 60), rng2.integers(60, n - 60)
        dem += disc(cx, cy, rng2.uniform(4, 6), rng2.uniform(0.3, 0.5))
        truth.append((400000.0 + cx * res, 5300000.0 - cy * res))
    for _ in range(40):                                      # Baumwurf-Störer (klein/scharf)
        cx, cy = rng2.integers(20, n - 20), rng2.integers(20, n - 20)
        dem += disc(cx, cy, rng2.uniform(1.0, 1.8), rng2.uniform(-0.6, 0.6))
    # Forstweg-Anschnitt (Bench am Hang) als FP-Falle
    dem[280:286, 50:550] += 0.4
    tile = lp.Tile(dem, res, 400000.0, 5300000.0, "EPSG:25832")
    return tile, truth


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validierung: P/R/F1 + Schwellen-Sweep")
    ap.add_argument("--candidates")
    ap.add_argument("--truth")
    ap.add_argument("--dem", help="DGM-Kachel für Sweep (.xyz/.tif)")
    ap.add_argument("--max-m", type=float, default=15.0, help="Matchradius Kandidat<->Wahrheit")
    ap.add_argument("--demo", action="store_true", help="synthetischer Selbsttest")
    args = ap.parse_args(argv)

    h_list = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40]
    bench_list = [0.0, 2.0, 3.0]

    if args.demo:
        tile, truth = make_labeled_demo()
        print(f"Synthetische Szene: {len(truth)} echte Meiler + 40 Störer + 1 Weg.")
        sweep(tile, truth, args.max_m, h_list, bench_list)
        return
    if args.dem and args.truth:
        tile = lp.load_tile(args.dem)
        truth = load_points(args.truth)
        print(f"{len(truth)} Ground-Truth-Punkte, DGM {args.dem}")
        sweep(tile, truth, args.max_m, h_list, bench_list)
        return
    if args.candidates and args.truth:
        cand = load_points(args.candidates)
        truth = load_points(args.truth)
        m = match(cand, truth, args.max_m)
        print(f"{len(cand)} Kandidaten vs. {len(truth)} Wahrheit (max_m={args.max_m}):")
        print(f"  Precision {m['precision']}  Recall {m['recall']}  F1 {m['f1']}  "
              f"(TP {m['tp']}, FP {m['fp']}, FN {m['fn']})")
        return
    ap.error("Entweder --demo, oder --dem+--truth (Sweep), oder --candidates+--truth (Metrik).")


if __name__ == "__main__":
    main()
