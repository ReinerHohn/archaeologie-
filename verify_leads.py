#!/usr/bin/env python3
"""Text-Leads automatisch gegen das LiDAR-Relief prüfen (die letzte Brücke).

Schließt den Kreis Text -> Fläche: nimmt die Sweet-Spots (dokumentiert, nicht
registriert), lädt an ihren Koordinaten die DGM1-Kacheln, lässt earthwork_detect
+ lidar_prospect auf einem Ausschnitt laufen und meldet, ob dort noch ein Erdwerk
(Umwallung/Wall/Plattform/Pinge) im Gelände steckt. Aus jedem Lead wird ein
'Relief: JA (x m, Typ) / NEIN'.

Lädt nur die Kacheln der Top-N-Leads (je 2x2-km-Kachel einmal).

Beispiel:
  python3 verify_leads.py --leads breisgau_sweetspots.geojson --top 6 --out data/leads
"""
import argparse
import glob
import json
import math
import os
import pathlib

import numpy as np

import lidar_prospect as lp
import earthwork_detect as ew
import fetch_dgm_bw as fd


def tile_1km_path(data_dir, x, y):
    e, n = int(x // 1000), int(y // 1000)
    hits = glob.glob(str(pathlib.Path(data_dir) / f"dgm1_32_{e}_{n}_1_bw_*.xyz"))
    return hits[0] if hits else None


def nearest_anomaly(tile, x, y, win_m=90):
    """Stärkste Anomalie (Umwallung/Wall/Ring/rund) im Umkreis + Abstand."""
    res = tile.res
    col = int(round((x - tile.x0) / res)); row = int(round((tile.y_top - y) / res))
    h = int(win_m / res)
    r0, r1 = max(0, row - h), min(tile.dem.shape[0], row + h)
    c0, c1 = max(0, col - h), min(tile.dem.shape[1], col + h)
    if r1 - r0 < 20 or c1 - c0 < 20:
        return None
    sub = lp.Tile(tile.dem[r0:r1, c0:c1].copy(), res,
                  tile.x0 + c0 * res, tile.y_top - r0 * res, tile.crs)
    found = []
    # Erdwerke (Wälle/Umwallungen/Ringe)
    segs, rings, _ = ew.detect_earthworks(sub, thr=0.2, min_len_m=10)
    for e in ew.cluster_enclosures(segs):
        found.append(("Umwallung", e["cx"], e["cy"], e["n_segmente"] + 2 * e["orient_klassen"]))
    for r in rings:
        bw, bh = r["bbox_m"]
        if r["fill"] < 0.35 and 8 <= min(bw, bh) and max(bw, bh) <= 150:
            found.append(("Ring", r["cx"], r["cy"], round((0.35 - r["fill"]) * 20 + 4, 1)))
    for s in sorted(segs, key=lambda s: -s["length_m"])[:3]:
        if s["length_m"] >= 18:
            found.append(("Wall", s["cx"], s["cy"], round(s["length_m"] / 10, 1)))
    # runde Formen (Meiler/Pingen/Plattform)
    hits, _ = lp.detect(sub, h_pos=0.2, h_neg=0.2, bench_margin=0.0)
    for hh in hits:
        found.append((hh["type"], hh["x"], hh["y"], hh["amplitude_m"]))
    if not found:
        return None
    best = min(found, key=lambda f: math.hypot(f[1] - x, f[2] - y))
    return {"typ": best[0], "dist_m": round(math.hypot(best[1] - x, best[2] - y)),
            "staerke": best[3], "x": round(best[1]), "y": round(best[2]),
            "n_anomalien": len(found)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sweet-Spot-Leads gegen LiDAR prüfen")
    ap.add_argument("--leads", required=True, help="Sweet-Spots-GeoJSON (EPSG:25832)")
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--win-m", type=float, default=90.0, help="Suchfenster um den Lead")
    ap.add_argument("--out", default="data/leads", help="Kachel-Verzeichnis")
    ap.add_argument("--max-tiles", type=int, default=12, help="Download-Obergrenze (Schutz)")
    args = ap.parse_args(argv)

    feats = json.loads(pathlib.Path(args.leads).read_text(encoding="utf-8"))["features"]
    feats.sort(key=lambda f: -f["properties"].get("score", 0))
    leads = feats[:args.top]
    outdir = pathlib.Path(args.out); outdir.mkdir(parents=True, exist_ok=True)

    # eindeutige 2-km-Kacheln bestimmen + laden
    tiles = {}
    for f in leads:
        x, y = f["geometry"]["coordinates"]
        tiles[fd.snap_sw(x, y)] = True
    tiles = list(tiles)[:args.max_tiles]
    print(f"{len(leads)} Leads -> {len(tiles)} DGM1-Kachel(n) laden …")
    for e_sw, n_sw in tiles:
        if glob.glob(str(outdir / f"dgm1_32_{e_sw+1}_{n_sw+1}_1_bw_*.xyz")) or \
           glob.glob(str(outdir / f"dgm1_32_{e_sw}_{n_sw}_1_bw_*.xyz")):
            continue
        try:
            fd.download_and_unzip(e_sw, n_sw, outdir, "dgm1")
            print(f"  geladen {e_sw}/{n_sw}")
        except Exception as ex:
            print(f"  FEHLER {e_sw}/{n_sw}: {ex}")

    print(f"\n{'Score':>5} {'Relief':>6} {'Lead':40} Befund")
    results = []
    for f in leads:
        x, y = f["geometry"]["coordinates"]
        p = f["properties"]
        lab = (p.get("label") or "(ohne Name)")[:38]
        tp = tile_1km_path(args.out, x, y)
        if not tp:
            print(f"{p.get('score',0):>5} {'?':>6} {lab:40} (keine Kachel)")
            results.append({**p, "relief": None}); continue
        try:
            anom = nearest_anomaly(lp.load_tile(tp), x, y, args.win_m)
        except Exception as ex:
            anom = None
            print("   (Fehler", ex, ")")
        if anom:
            print(f"{p.get('score',0):>5} {'JA':>6} {lab:40} {anom['typ']} {anom['dist_m']}m "
                  f"(Stärke {anom['staerke']}, {anom['n_anomalien']} Anomalien im Fenster)")
        else:
            print(f"{p.get('score',0):>5} {'nein':>6} {lab:40} kein Erdwerk im {args.win_m:.0f}-m-Fenster")
        results.append({**p, "x": x, "y": y, "relief": anom})

    ja = sum(1 for r in results if r.get("relief"))
    print(f"\n{ja}/{len(results)} Leads zeigen ein Relief-Erdwerk am dokumentierten Ort.")
    pathlib.Path("leads_verifiziert.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("-> leads_verifiziert.json")


if __name__ == "__main__":
    main()
