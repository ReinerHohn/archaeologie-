#!/usr/bin/env python3
"""Daten-FUSION: versteckte 'low-hanging fruit'-Archäologie aufspüren.

Ein Befund ist dann ein heißer Kandidat, wenn mehrere UNABHÄNGIGE Datenquellen
zusammenfallen. Dieses Werkzeug fasst sie zu einem Score zusammen:

  Erdwerk (earthwork_detect: Umwallung/Ring)         <- Form im LiDAR
  × im WALD (OSM landuse=forest/natural=wood)         <- Kontext
  × NICHT an moderner Straße (OSM highway, Puffer)     <- kein Weg-Anschnitt
  × NICHT im amtlichen Verzeichnis (LAD BW WMS)        <- also potenziell neu
  + Bonus bei historischem HINWEIS in der Nähe         <- Flurname/OSM-historic
    (Burgstall, Schanze, Ringwall, Hügelgrab, Wüstung, ...)

Ausgabe: <name>_funde.geojson + .csv (nach Score sortiert) und optional ein
Kontaktbogen der Top-Treffer (--figures, braucht die DGM-Kacheln).

Reine Wiederverwendung der getesteten Module (earthwork_detect, forest_filter,
denkmal_check). Beispiel:
  python3 discovery_score.py --data data/freiburg_ost --name freiburg --figures
"""
import argparse
import csv
import glob
import json
import math
import pathlib
import sys

import numpy as np

import lidar_prospect as lp
import earthwork_detect as ew
import forest_filter as ff
import denkmal_check as dk

# verräterische Namensbestandteile (archäologisch), case-insensitiv
HINT_RX = ("Burgstall|Burgstelle|Altschloss|Hochburg|Schanz|Ringwall|Wallburg|"
           "Heidenschloss|Heidenmauer|Keltensch|Römer|Roemer|Tumulus|Hügelgrab|"
           "Huegelgrab|Hünengrab|Huenengrab|Letzi|Turmhügel|Turmhuegel|Motte|"
           "Verschanzung|Wüstung|Wuestung|Landgraben|Abschnittswall|Altenburg|Burg")


def collect_candidates(data_dir):
    """Erdwerk-Kandidaten (Umwallungen + geschlossene Ringe) je Kachel sammeln."""
    cands = []
    for path in sorted(glob.glob(str(pathlib.Path(data_dir) / "*.xyz"))):
        tile = lp.load_tile(path)
        segs, rings, _ = ew.detect_earthworks(tile, thr=0.2, min_len_m=12)
        for e in ew.cluster_enclosures(segs):
            score = e["n_segmente"] + 2 * e["orient_klassen"]
            cands.append({"x": e["cx"], "y": e["cy"], "kind": "umwallung",
                          "base": float(score), "tile": path,
                          "detail": f"{e['n_segmente']} Segmente/{e['orient_klassen']} Richt."})
        for r in rings:
            bw, bh = r["bbox_m"]
            aspect = max(bw, bh) / max(min(bw, bh), 1)
            if r["fill"] < 0.30 and 10 <= min(bw, bh) and max(bw, bh) <= 120 and aspect <= 3.0:
                score = (0.30 - r["fill"]) * 20 + 5
                cands.append({"x": r["cx"], "y": r["cy"], "kind": "ring",
                              "base": float(round(score, 1)), "tile": path,
                              "detail": f"Ring {bw:.0f}x{bh:.0f} m, fill {r['fill']}"})
    return cands


def fetch_hints(s, w, n, e):
    q = (f'[out:json][timeout:90];('
         f'nwr["name"~"{HINT_RX}",i]({s},{w},{n},{e});'
         f'nwr["historic"]({s},{w},{n},{e});'
         f');out center tags;')
    try:
        osm = ff._overpass(q)
    except Exception as ex:
        print("  (Hinweise/Overpass nicht erreichbar:", ex, ")")
        return []
    import re
    rx = re.compile(HINT_RX, re.I)
    # NUR archäologisch relevante historic-Werte (sonst Rauschen wie
    # locomotive/monument/memorial/Vereinsnamen)
    hist_ok = {"archaeological_site", "ruins", "castle", "fort", "fortification",
               "city_gate", "citywalls", "tower", "manor", "monastery",
               "tumulus", "hillfort", "rune_stone", "mine", "adit", "mine_shaft",
               "boundary_stone" if False else "charcoal_pile"}
    out = []
    for el in osm.get("elements", []):
        t = el.get("tags", {})
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None:
            continue
        # Straßen/Wege ausschließen: deren Name verweist oft nur auf ein ENTFERNTES
        # Ziel (z.B. 'Waldfahrstraße …-Kyburg') und täuscht einen Hinweis vor.
        if t.get("highway"):
            continue
        name = t.get("name", "")
        hist = t.get("historic", "")
        if rx.search(name) or hist in hist_ok:
            out.append((lon, lat, name or hist))
    return out


def nearest(px, py, pts_xy):
    best = (1e9, None)
    for (x, y, lab) in pts_xy:
        d = math.hypot(px - x, py - y)
        if d < best[0]:
            best = (d, lab)
    return best


def main(argv=None):
    ap = argparse.ArgumentParser(description="Daten-Fusion: versteckte Archäologie-Kandidaten")
    ap.add_argument("--data", required=True, help="Verzeichnis mit DGM-Kacheln (*.xyz)")
    ap.add_argument("--name", default="region")
    ap.add_argument("--exclude-roads-m", type=float, default=20.0)
    ap.add_argument("--register-m", type=float, default=30.0, help="Abstand, ab dem 'bekannt'")
    ap.add_argument("--hint-m", type=float, default=300.0, help="Hinweis-Bonusradius")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--figures", action="store_true", help="Kontaktbogen der Top-Treffer")
    args = ap.parse_args(argv)

    cands = collect_candidates(args.data)
    if not cands:
        sys.exit("Keine Erdwerk-Kandidaten gefunden.")
    px = np.array([c["x"] for c in cands]); py = np.array([c["y"] for c in cands])
    print(f"{len(cands)} Erdwerk-Rohkandidaten aus {args.data}")

    pad = 150
    minx, maxx = px.min() - pad, px.max() + pad
    miny, maxy = py.min() - pad, py.max() + pad
    lon, lat = ff.to_lonlat(np.array([minx, maxx]), np.array([miny, maxy]))
    s, w, n, e = lat.min(), lon.min(), lat.max(), lon.max()

    # --- Wald ---
    in_forest = np.ones(len(cands), bool)
    try:
        rings_ll = ff.polygons_from_osm(ff.fetch_forest(s, w, n, e))
        rings = []
        for ring in rings_ll:
            rx, ry = ff.to_utm([p[0] for p in ring], [p[1] for p in ring])
            rings.append(np.column_stack([rx, ry]))
        fmask = np.zeros(len(cands), bool)
        for ring in rings:
            fmask |= ff.point_in_ring(px, py, ring)
        in_forest = fmask
        print(f"  Wald: {in_forest.sum()}/{len(cands)} im Wald ({len(rings)} Polygone)")
    except Exception as ex:
        print("  (Wald übersprungen:", ex, ")")

    # --- Straßen ---
    road_ok = np.ones(len(cands), bool)
    try:
        segs = ff.fetch_roads(s, w, n, e)
        slon = np.array([g[0] for g in segs] + [g[2] for g in segs])
        slat = np.array([g[1] for g in segs] + [g[3] for g in segs])
        sx, sy = ff.to_utm(slon, slat); ns = len(segs)
        ax, ay, bx, by = sx[:ns], sy[:ns], sx[ns:], sy[ns:]
        for i in range(len(cands)):
            road_ok[i] = ff.seg_dist_min(px[i], py[i], ax, ay, bx, by) >= args.exclude_roads_m
        print(f"  Wege: {road_ok.sum()}/{len(cands)} abseits (>= {args.exclude_roads_m:.0f} m)")
    except Exception as ex:
        print("  (Wege übersprungen:", ex, ")")

    # --- amtliches Verzeichnis ---
    known = np.zeros(len(cands), bool)
    try:
        wpx = max(1, int((maxx - minx) / 2)); hpx = max(1, int((maxy - miny) / 2))
        if max(wpx, hpx) > 4000:
            sc = 4000 / max(wpx, hpx); wpx, hpx = int(wpx * sc), int(hpx * sc)
        dmask = dk.wms_getmap(dk.LYR_DENK, minx, miny, maxx, maxy, wpx, hpx)
        try:  # auch Bau-/Kunstdenkmale (z.B. Burgruinen) gegenprüfen
            dmask = dmask | dk.wms_getmap(dk.LYR_BK, minx, miny, maxx, maxy, wpx, hpx, base=dk.WMS_BK)
        except Exception as ex:
            print("  (Bau-/Kunstdenkmal-Layer übersprungen:", ex, ")")
        rr = args.register_m / ((maxx - minx) / wpx)
        for i in range(len(cands)):
            col = (px[i] - minx) / (maxx - minx) * wpx
            row = (maxy - py[i]) / (maxy - miny) * hpx
            c0, c1 = int(max(0, col - rr)), int(min(wpx, col + rr + 1))
            r0, r1 = int(max(0, row - rr)), int(min(hpx, row + rr + 1))
            known[i] = bool(dmask[r0:r1, c0:c1].any())
        print(f"  Amt: {known.sum()}/{len(cands)} bereits eingetragen")
    except Exception as ex:
        print("  (Denkmal-WMS übersprungen:", ex, ")")

    # --- historische Hinweise ---
    hints = fetch_hints(s, w, n, e)
    hints_xy = []
    if hints:
        hx, hy = ff.to_utm([h[0] for h in hints], [h[1] for h in hints])
        hints_xy = list(zip(hx, hy, [h[2] for h in hints]))
    print(f"  Hinweise (Flurnamen/historic): {len(hints_xy)}")

    # --- Fusion: filtern + scoren ---
    kept = []
    for i, c in enumerate(cands):
        if not in_forest[i] or not road_ok[i] or known[i]:
            continue
        score = c["base"]
        hint_d, hint_lab = nearest(px[i], py[i], hints_xy) if hints_xy else (1e9, None)
        if hint_d <= args.hint_m:
            score += 6 if hint_d <= 150 else 3
        c2 = dict(c)
        c2["score"] = round(score, 1)
        c2["hint"] = hint_lab if hint_d <= args.hint_m else ""
        c2["hint_m"] = round(hint_d) if hint_d < 1e8 else None
        kept.append(c2)
    kept.sort(key=lambda c: -c["score"])

    feats = [{"type": "Feature",
              "geometry": {"type": "Point", "coordinates": [c["x"], c["y"]]},
              "properties": {k: c[k] for k in ("kind", "score", "base", "detail", "hint", "hint_m")}}
             for c in kept]
    out = {"type": "FeatureCollection",
           "crs": {"type": "name", "properties": {"name": "EPSG:25832"}}, "features": feats}
    gj = f"{args.name}_funde.geojson"
    pathlib.Path(gj).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    with open(f"{args.name}_funde.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f); wr.writerow(["rang", "kind", "score", "x", "y", "hint", "hint_m", "detail"])
        for i, c in enumerate(kept, 1):
            wr.writerow([i, c["kind"], c["score"], round(c["x"]), round(c["y"]),
                         c["hint"], c["hint_m"], c["detail"]])

    print("\n" + "=" * 70)
    print(f"FUSIONS-ERGEBNIS: {len(kept)} versteckte Kandidaten "
          f"(Wald & wegfern & amtlich UNbekannt), nach Score:")
    print(f"{'#':>2} {'Score':>5} {'Art':10} {'Ost':>7} {'Nord':>8}  Hinweis")
    for i, c in enumerate(kept[:args.top], 1):
        print(f"{i:>2} {c['score']:>5} {c['kind']:10} {c['x']:7.0f} {c['y']:8.0f}  "
              f"{(c['hint'] + f' ({c['hint_m']}m)') if c['hint'] else '—'}")
    print(f"\n-> {gj}, {args.name}_funde.csv")

    if args.figures and kept:
        render_contact(kept[:args.top], args.name)


def render_contact(cands, name):
    try:
        from PIL import Image, ImageDraw
    except Exception:
        print("  (Figures: Pillow fehlt)"); return
    tiles = {}

    def gt(p):
        if p not in tiles:
            tiles[p] = lp.load_tile(p)
        return tiles[p]
    S, HALF = 240, 70
    cells = []
    for i, c in enumerate(cands, 1):
        t = gt(c["tile"]); res = t.res
        col = int(round((c["x"] - t.x0) / res)); row = int(round((t.y_top - c["y"]) / res))
        h = int(HALF / res)
        r0, r1 = max(0, row - h), min(t.dem.shape[0], row + h)
        c0, c1 = max(0, col - h), min(t.dem.shape[1], col + h)
        win = t.dem[r0:r1, c0:c1]; win = np.where(np.isnan(win), np.nanmedian(win), win)
        hs = (lp.hillshade(win, res) * 255).astype(np.uint8)
        im = Image.fromarray(hs).convert("RGB").resize((S, S), Image.BILINEAR)
        dr = ImageDraw.Draw(im)
        cxp = int((col - c0) / win.shape[1] * S); cyp = int((row - r0) / win.shape[0] * S)
        dr.ellipse([cxp - 10, cyp - 10, cxp + 10, cyp + 10], outline=(255, 50, 50), width=2)
        dr.rectangle([0, 0, 118, 15], fill=(0, 0, 0))
        dr.text((2, 2), f"#{i} {c['kind'][:4]} S{c['score']}", fill=(255, 255, 0))
        cells.append(im)
    cols = 5; rows = (len(cells) + cols - 1) // cols
    grid = Image.new("RGB", (cols * (S + 4) + 4, rows * (S + 4) + 4), (15, 15, 15))
    for i, im in enumerate(cells):
        grid.paste(im, ((i % cols) * (S + 4) + 4, (i // cols) * (S + 4) + 4))
    outp = f"docs/{name}_funde_kontaktbogen.png"
    pathlib.Path("docs").mkdir(exist_ok=True)
    grid.save(outp)
    print(f"  -> {outp}")


if __name__ == "__main__":
    main()
