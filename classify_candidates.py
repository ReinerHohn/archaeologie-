#!/usr/bin/env python3
"""Merkmalsbasierter Klassifikator gegen den PRECISION-Engpass.

Der Detektor hat guten Recall, aber viele False Positives (Baumwurf-Höcker u.ä.).
Dieses Werkzeug extrahiert je Kandidat FORMMERKMALE aus dem DGM und lernt daraus
'echte Plattform vs. Störer' (Logistische Regression in reinem numpy, kein
sklearn nötig). Trainierbar auf gelabelten Daten (synthetisch jetzt, RCH später).

Merkmale (aus Local-Relief-Model + Hangneigung um den Kandidaten):
  amp        LRM-Höhe im Zentrum
  flat_in    mittlere Hangneigung im Inneren  (Plattform = flach -> klein)
  rough_in   Rauheit (LRM-Std) im Inneren     (Plattform = glatt -> klein)
  peaked     Zentrum / Ring                   (Baumwurf = spitz -> groß)
  symmetry   Rund-Symmetrie auf dem Ring       (Plattform -> groß)
  ctx_slope  Hangneigung im Umfeld
  size       geschätzter Radius

Modi:
  python3 classify_candidates.py --demo                  # Train Szene A, Test Szene B
  python3 classify_candidates.py --train dgm.xyz --truth gt.geojson --out model.json
  python3 classify_candidates.py --apply dgm.xyz --candidates c.geojson --model model.json
"""
import argparse
import json
import pathlib
import sys

import numpy as np

import lidar_prospect as lp
import validate as V

FEATS = ["amp", "flat_in", "rough_in", "peaked", "symmetry", "ctx_slope", "size"]


def tile_fields(tile):
    dem = np.where(np.isnan(tile.dem), np.nanmedian(tile.dem), tile.dem)
    lrm = dem - lp.box_mean(dem, max(1, int(round(15 / tile.res))))
    lrm = lp.box_mean(lrm, max(1, int(round(1.5 / tile.res))))
    slp = lp.slope_deg(dem, tile.res)
    return lrm, slp


def features(tile, x, y, lrm, slp):
    res = tile.res
    col = int(round((x - tile.x0) / res)); row = int(round((tile.y_top - y) / res))
    R = int(round(12 / res))
    r0, r1 = max(0, row - R), min(lrm.shape[0], row + R + 1)
    c0, c1 = max(0, col - R), min(lrm.shape[1], col + R + 1)
    wl = lrm[r0:r1, c0:c1]; ws = slp[r0:r1, c0:c1]
    yy, xx = np.mgrid[r0:r1, c0:c1]
    dist = np.hypot((yy - row) * res, (xx - col) * res)
    inner = dist <= 4.0
    ring = (dist >= 5.0) & (dist <= 8.0)
    ctx = (dist >= 9.0) & (dist <= 12.0)
    center = dist <= 2.0
    amp = float(wl[center].mean()) if center.any() else 0.0
    ring_mean = float(wl[ring].mean()) if ring.any() else 0.0
    return np.array([
        amp,
        float(ws[inner].mean()) if inner.any() else 0.0,          # flat_in
        float(wl[inner].std()) if inner.any() else 0.0,           # rough_in
        amp / (abs(ring_mean) + 0.05),                            # peaked
        1.0 / (1.0 + (float(wl[ring].std()) if ring.any() else 1.0)),  # symmetry
        float(ws[ctx].mean()) if ctx.any() else 0.0,              # ctx_slope
        float(np.sqrt(inner.sum()) * res / 2),                    # size-proxy
    ])


def candidates_with_labels(tile, truth_xy, h_pos=0.15, bench=0.0, max_m=15.0):
    hits, _ = lp.detect(tile, h_pos=h_pos, h_neg=h_pos, bench_margin=bench)
    hits = [h for h in hits if h["type"] == "meiler"]
    lrm, slp = tile_fields(tile)
    X, y, xy = [], [], []
    for h in hits:
        X.append(features(tile, h["x"], h["y"], lrm, slp))
        d = min((np.hypot(h["x"] - tx, h["y"] - ty) for tx, ty in truth_xy), default=1e9)
        y.append(1 if d <= max_m else 0)
        xy.append((h["x"], h["y"]))
    return np.array(X), np.array(y), xy


def fit_logreg(X, yv, iters=1500, lr=0.3, l2=1e-2):
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Xs = np.hstack([(X - mu) / sd, np.ones((len(X), 1))])
    w = np.zeros(Xs.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Xs @ w))
        g = Xs.T @ (p - yv) / len(yv) + l2 * np.r_[w[:-1], 0]
        w -= lr * g
    return {"w": w.tolist(), "mu": mu.tolist(), "sd": sd.tolist(), "feats": FEATS}


def predict(model, X):
    w = np.array(model["w"]); mu = np.array(model["mu"]); sd = np.array(model["sd"])
    Xs = np.hstack([(X - mu) / sd, np.ones((len(X), 1))])
    return 1 / (1 + np.exp(-Xs @ w))


def demo():
    tr, gt_tr = V.make_labeled_demo(seed=7)
    te, gt_te = V.make_labeled_demo(seed=21)
    Xtr, ytr, _ = candidates_with_labels(tr, gt_tr)
    Xte, yte, xyte = candidates_with_labels(te, gt_te)
    print(f"Training (Szene A): {len(ytr)} Kandidaten, {int(ytr.sum())} echt.")
    print(f"Test     (Szene B): {len(yte)} Kandidaten, {int(yte.sum())} echt.")
    model = fit_logreg(Xtr, ytr)

    base = V.match(xyte, gt_te, 15.0)
    prob = predict(model, Xte)
    keep = [xyte[i] for i in range(len(xyte)) if prob[i] >= 0.5]
    after = V.match(keep, gt_te, 15.0)
    print("\n            Precision  Recall   F1   (TP/FP/FN)")
    print(f"  Detektor roh  {base['precision']:.2f}     {base['recall']:.2f}   "
          f"{base['f1']:.2f}   {base['tp']}/{base['fp']}/{base['fn']}")
    print(f"  + Klassifik.  {after['precision']:.2f}     {after['recall']:.2f}   "
          f"{after['f1']:.2f}   {after['tp']}/{after['fp']}/{after['fn']}")
    print("\nGelernte Gewichte (standardisiert):")
    for f, wv in zip(FEATS, model["w"]):
        print(f"  {f:10} {wv:+.2f}")
    return base, after


def main(argv=None):
    ap = argparse.ArgumentParser(description="Kandidaten-Klassifikator (Precision-Booster)")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--train"); ap.add_argument("--truth")
    ap.add_argument("--apply"); ap.add_argument("--candidates"); ap.add_argument("--model")
    ap.add_argument("--out", default="model_meiler.json")
    ap.add_argument("--min-prob", type=float, default=0.5)
    args = ap.parse_args(argv)

    if args.demo:
        demo(); return
    if args.train and args.truth:
        tile = lp.load_tile(args.train); truth = V.load_points(args.truth)
        X, y, _ = candidates_with_labels(tile, truth)
        if y.sum() == 0:
            sys.exit("Keine positiven Beispiele (Truth zu weit?).")
        model = fit_logreg(X, y)
        pathlib.Path(args.out).write_text(json.dumps(model), encoding="utf-8")
        print(f"Modell trainiert auf {len(y)} Kandidaten ({int(y.sum())} echt) -> {args.out}")
        return
    if args.apply and args.candidates and args.model:
        tile = lp.load_tile(args.apply)
        model = json.loads(pathlib.Path(args.model).read_text())
        cand = V.load_points(args.candidates)
        lrm, slp = tile_fields(tile)
        X = np.array([features(tile, x, y, lrm, slp) for x, y in cand])
        prob = predict(model, X)
        keep = [(cand[i], round(float(prob[i]), 2)) for i in range(len(cand)) if prob[i] >= args.min_prob]
        print(f"{len(keep)}/{len(cand)} Kandidaten über Prob {args.min_prob}")
        out = {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": tile.crs}},
               "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": list(xy)},
                             "properties": {"prob": p}} for xy, p in keep]}
        pathlib.Path("klassifiziert.geojson").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        print("-> klassifiziert.geojson")
        return
    ap.error("--demo, oder --train+--truth, oder --apply+--candidates+--model.")


if __name__ == "__main__":
    main()
