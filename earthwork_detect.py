#!/usr/bin/env python3
"""Erkennt LINEARE/RECHTECKIGE Erdwerke (Wälle, Umwallungen, Gräben-Ränder).

Ergänzt lidar_prospect.py (der nur RUNDE Meiler/Pingen findet). Der Anlass war
das Rosskopf-Rechteck, das der Punkt-Detektor nur zufällig am Rand streifte.

Idee: Wälle/Ramparts sind schmale, LANGE Erhebungen im Local-Relief-Model.
  1. LRM = DGM − großräumiger Mittelwert.
  2. Grat-Test (ridge): Pixel ist Wall-Grat, wenn das LRM dort über einen
     Schwellwert steigt UND entlang mindestens einer Richtung höher ist als die
     beiden Nachbarn im Abstand d (schmaler Rücken).
  3. Zusammenhängende Grat-Pixel labeln (BFS), je Komponente Länge/Breite/
     Ausrichtung per Hauptachsen (PCA). Lange, schmale = Wall-SEGMENTE.
  4. Segmente, die eng beieinander liegen und verschiedene Richtungen haben,
     bilden eine UMWALLUNG/Enclosure (z.B. Rechteckanlage).

Ausgabe: <name>_erdwerke.geojson (LineStrings der Wall-Segmente + Enclosure-
Punkte) und optional ein Overlay-PNG. numpy (+Pillow fürs PNG).
Beispiel:
  python3 earthwork_detect.py data/freiburg_ost/dgm1_32_419_5321_1_bw_2017.xyz --png
"""
import argparse
import json
import math
import pathlib
import sys

import numpy as np

import lidar_prospect as lp  # box_mean, load_tile, hillshade


def ridge_mask(lrm, d, thr, margin):
    """Grat-Pixel: lokaler Rücken in mind. einer von 4 Richtungen."""
    out = np.zeros(lrm.shape, dtype=bool)
    for dr, dc in ((0, d), (d, 0), (d, d), (d, -d)):
        plus = np.roll(np.roll(lrm, -dr, 0), -dc, 1)
        minus = np.roll(np.roll(lrm, dr, 0), dc, 1)
        out |= ((lrm - plus) > margin) & ((lrm - minus) > margin)
    out &= lrm > thr
    out[:d, :] = out[-d:, :] = out[:, :d] = out[:, -d:] = False  # Randwrap killen
    return out


def label_components(mask):
    """8-Konnex-Zusammenhangskomponenten per BFS über die True-Pixel."""
    h, w = mask.shape
    lab = np.zeros((h, w), dtype=np.int32)
    comps = []
    nxt = 1
    rs, cs = np.where(mask)
    coordset = mask  # bool lookup
    from collections import deque
    for r0, c0 in zip(rs, cs):
        if lab[r0, c0]:
            continue
        q = deque([(r0, c0)])
        lab[r0, c0] = nxt
        pix = []
        while q:
            r, c = q.popleft()
            pix.append((r, c))
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < h and 0 <= cc < w and coordset[rr, cc] and not lab[rr, cc]:
                        lab[rr, cc] = nxt
                        q.append((rr, cc))
        comps.append(np.array(pix))
        nxt += 1
    return comps


def axis_stats(pix, res):
    """Länge/Breite/Ausrichtung einer Pixelmenge via Hauptachsen (PCA)."""
    ys = pix[:, 0].astype(float)
    xs = pix[:, 1].astype(float)
    cx, cy = xs.mean(), ys.mean()
    cov = np.cov(np.vstack([xs - cx, ys - cy]))
    if cov.shape != (2, 2):
        return 0.0, 0.0, 0.0, (cx, cy), (cx, cy)
    evals, evecs = np.linalg.eigh(cov)
    major = evecs[:, np.argmax(evals)]
    proj = (xs - cx) * major[0] + (ys - cy) * major[1]
    minr = evecs[:, np.argmin(evals)]
    projm = (xs - cx) * minr[0] + (ys - cy) * minr[1]
    length = (proj.max() - proj.min()) * res
    width = max((projm.max() - projm.min()) * res, res)
    ang = math.degrees(math.atan2(major[1], major[0])) % 180
    p0 = (cx + major[0] * proj.min(), cy + major[1] * proj.min())
    p1 = (cx + major[0] * proj.max(), cy + major[1] * proj.max())
    return length, width, ang, p0, p1


def detect_earthworks(tile, bg_m=25.0, smooth_m=1.5, ridge_d_m=2.0,
                      thr=0.18, margin=0.08, min_len_m=10.0, min_elong=2.5,
                      max_width_m=12.0):
    dem = tile.dem
    res = tile.res
    filled = np.where(np.isnan(dem), np.nanmedian(dem), dem)
    lrm = filled - lp.box_mean(filled, max(1, int(round(bg_m / res))))
    if smooth_m > 0:
        lrm = lp.box_mean(lrm, max(1, int(round(smooth_m / res))))
    d = max(1, int(round(ridge_d_m / res)))
    mask = ridge_mask(lrm, d, thr, margin)
    comps = label_components(mask)

    def to_xy(p):
        return [round(tile.x0 + p[0] * res, 1), round(tile.y_top - p[1] * res, 1)]

    segs, rings = [], []
    for pix in comps:
        if len(pix) < 8:
            continue
        length, width, ang, p0, p1 = axis_stats(pix, res)
        cx = tile.x0 + pix[:, 1].mean() * res
        cy = tile.y_top - pix[:, 0].mean() * res
        if length >= min_len_m and width <= max_width_m and length / width >= min_elong:
            segs.append({"length_m": round(length, 1), "width_m": round(width, 1),
                         "orient_deg": round(ang, 0), "p0": to_xy(p0), "p1": to_xy(p1),
                         "cx": cx, "cy": cy})
            continue
        # Ring-/Umriss-Komponente: große, HOHLE Fläche (geschlossene Umwallung)
        bw = (pix[:, 1].max() - pix[:, 1].min() + 1) * res
        bh = (pix[:, 0].max() - pix[:, 0].min() + 1) * res
        fill = len(pix) / (((pix[:, 1].max() - pix[:, 1].min() + 1) *
                            (pix[:, 0].max() - pix[:, 0].min() + 1)) or 1)
        if (fill < 0.40 and len(pix) >= 20 and
                6 <= min(bw, bh) and max(bw, bh) <= 200):
            rings.append({"cx": round(cx, 1), "cy": round(cy, 1),
                          "bbox_m": [round(bw, 1), round(bh, 1)], "fill": round(fill, 2),
                          "n_pixel": int(len(pix))})
    return segs, rings, mask


def cluster_enclosures(segs, radius_m=45.0, min_segs=4, min_orient_bins=3):
    """Dicht stehende, MEHRFACH orientierte Segmente = Umwallung/Enclosure.

    Verlangt genug Segmente UND ≥min_orient_bins verschiedene Richtungen (45°-
    Klassen) in Reichweite -> grenzt eine Fläche ein (Ecke/Umriss), statt nur
    paralleler Wege/Hangkanten. Sortiert nach „Geschlossenheit" (Segmentzahl).
    """
    used = [False] * len(segs)
    out = []
    order = sorted(range(len(segs)), key=lambda i: -segs[i]["length_m"])
    for i in order:
        if used[i]:
            continue
        s = segs[i]
        grp = [j for j, t in enumerate(segs)
               if not used[j] and math.hypot(s["cx"] - t["cx"], s["cy"] - t["cy"]) <= radius_m]
        if len(grp) < min_segs:
            continue
        oris = {int(segs[k]["orient_deg"] // 45) % 4 for k in grp}
        if len(oris) < min_orient_bins:
            continue
        for k in grp:
            used[k] = True
        cx = float(np.mean([segs[k]["cx"] for k in grp]))
        cy = float(np.mean([segs[k]["cy"] for k in grp]))
        out.append({"cx": round(cx, 1), "cy": round(cy, 1),
                    "n_segmente": len(grp), "orient_klassen": len(oris),
                    "laenge_summe_m": round(sum(segs[k]["length_m"] for k in grp), 1)})
    out.sort(key=lambda e: (-e["orient_klassen"], -e["n_segmente"]))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lineare/rechteckige Erdwerke erkennen")
    ap.add_argument("tiles", nargs="+", help="DGM-Kacheln (.xyz/.tif)")
    ap.add_argument("--thr", type=float, default=0.18, help="LRM-Grat-Schwelle (m)")
    ap.add_argument("--min-len", type=float, default=10.0, help="Mindest-Walllänge (m)")
    ap.add_argument("--png", action="store_true", help="Overlay-PNG schreiben")
    args = ap.parse_args(argv)

    allsegs = []
    for path in args.tiles:
        tile = lp.load_tile(path)
        segs, rings, mask = detect_earthworks(tile, thr=args.thr, min_len_m=args.min_len)
        encl = cluster_enclosures(segs)
        for r in rings:  # geschlossene Umriss-Komponenten direkt als Umwallung
            encl.append({"cx": r["cx"], "cy": r["cy"], "n_segmente": 1,
                         "orient_klassen": 4, "laenge_summe_m": None, "bbox_m": r["bbox_m"]})
        stem = pathlib.Path(path).stem
        print(f"{stem}: {len(segs)} Wall-Segmente, {len(rings)} Ring-Umriss(e), "
              f"{len(encl)} Umwallungs-Kandidat(en)")
        for e in encl:
            print(f"   Enclosure @ {e['cx']:.0f}/{e['cy']:.0f}  "
                  f"({e['n_segmente']} Segmente, Summe {e['laenge_summe_m']} m)")
        feats = []
        for s in segs:
            feats.append({"type": "Feature",
                          "geometry": {"type": "LineString", "coordinates": [s["p0"], s["p1"]]},
                          "properties": {k: s[k] for k in ("length_m", "width_m", "orient_deg")}})
        for e in encl:
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [e["cx"], e["cy"]]},
                          "properties": {"kind": "enclosure", **e}})
        out = {"type": "FeatureCollection",
               "crs": {"type": "name", "properties": {"name": tile.crs}}, "features": feats}
        outp = f"{stem}_erdwerke.geojson"
        pathlib.Path(outp).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        print(f"   -> {outp}")
        allsegs += segs

        if args.png:
            try:
                from PIL import Image
                filled = np.where(np.isnan(tile.dem), np.nanmedian(tile.dem), tile.dem)
                hs = (lp.hillshade(filled, tile.res) * 255).astype(np.uint8)
                rgb = np.stack([hs, hs, hs], -1)
                rgb[mask] = [255, 60, 60]
                Image.fromarray(rgb).save(f"{stem}_erdwerke.png")
                print(f"   -> {stem}_erdwerke.png")
            except Exception as e:
                print("   (PNG übersprungen:", e, ")")

    if not allsegs:
        print("Keine Wall-Segmente gefunden (ggf. --thr senken).")


if __name__ == "__main__":
    main()
