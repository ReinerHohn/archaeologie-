#!/usr/bin/env python3
"""Filtert LiDAR-Kandidaten auf WALDflächen (OSM) – der große Qualitätshebel.

Köhlerei-Meilerplätze liegen im Wald; die meisten Fehlalarme (Feld-/Talboden-/
Siedlungs-Mikrorelief) nicht. Dieses Skript holt kostenlose OSM-Waldpolygone
(Overpass: landuse=forest, natural=wood) für die Bounding-Box der Kandidaten und
behält nur Punkte, die IN einem Waldpolygon liegen.

Eingabe: eine Kandidaten-GeoJSON aus lidar_prospect.py (Koordinaten EPSG:25832).
Ausgabe: <name>_wald.geojson (nur Kandidaten im Wald).

Braucht: numpy (Pflicht), rasterio (für UTM<->lat/lon, meist vorhanden).
Beispiel:
  python3 forest_filter.py freiburg_ost_kandidaten.geojson
"""
import argparse
import json
import pathlib
import sys
import urllib.parse
import urllib.request

import numpy as np

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
UA = {"User-Agent": "archaeologie-lidar/1.0 (research; charcoal-hearth prospection)"}


def to_lonlat(xs, ys, src="EPSG:25832"):
    from rasterio.warp import transform
    lon, lat = transform(src, "EPSG:4326", list(xs), list(ys))
    return np.array(lon), np.array(lat)


def to_utm(lons, lats, dst="EPSG:25832"):
    from rasterio.warp import transform
    x, y = transform("EPSG:4326", dst, list(lons), list(lats))
    return np.array(x), np.array(y)


def _overpass(query):
    data = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for ep in OVERPASS_ENDPOINTS:
        for attempt in range(2):
            try:
                req = urllib.request.Request(ep, data=data, headers=UA)
                with urllib.request.urlopen(req, timeout=180) as r:
                    return json.loads(r.read())
            except Exception as ex:
                last = ex
                print(f"  Overpass {ep} Versuch {attempt+1}: {ex}")
    raise last


def fetch_roads(s, w, n, e):
    q = (f"[out:json][timeout:120];("
         f'way["highway"~"^(track|path|service|unclassified|residential|footway)$"]({s},{w},{n},{e});'
         f");out geom;")
    osm = _overpass(q)
    segs = []
    for el in osm.get("elements", []):
        g = el.get("geometry") or []
        for a, b in zip(g[:-1], g[1:]):
            segs.append((a["lon"], a["lat"], b["lon"], b["lat"]))
    return segs


def seg_dist_min(px, py, ax, ay, bx, by):
    """Kürzester Abstand Punkt (px,py) zu Strecken A-B (Arrays), Minimum. UTM (m)."""
    dx = bx - ax
    dy = by - ay
    L2 = dx * dx + dy * dy
    t = np.where(L2 > 0, ((px - ax) * dx + (py - ay) * dy) / np.where(L2 > 0, L2, 1), 0.0)
    t = np.clip(t, 0.0, 1.0)
    cx = ax + t * dx
    cy = ay + t * dy
    return np.hypot(px - cx, py - cy).min()


def fetch_forest(s, w, n, e):
    q = (f"[out:json][timeout:90];("
         f'way["landuse"="forest"]({s},{w},{n},{e});'
         f'relation["landuse"="forest"]({s},{w},{n},{e});'
         f'way["natural"="wood"]({s},{w},{n},{e});'
         f'relation["natural"="wood"]({s},{w},{n},{e});'
         f");out geom;")
    return _overpass(q)


def polygons_from_osm(osm):
    """Liefert Listen von (lon,lat)-Ringen aus ways und relation-outer-members."""
    rings = []
    for el in osm.get("elements", []):
        if el.get("type") == "way" and el.get("geometry"):
            rings.append([(p["lon"], p["lat"]) for p in el["geometry"]])
        elif el.get("type") == "relation":
            for m in el.get("members", []):
                if m.get("role") in ("outer", "") and m.get("geometry"):
                    rings.append([(p["lon"], p["lat"]) for p in m["geometry"]])
    return [r for r in rings if len(r) >= 4]


def point_in_ring(px, py, ring):
    """Ray-Casting, vektorisiert über alle Punkte. ring: Nx2 (x,y)."""
    x = ring[:, 0]; y = ring[:, 1]
    inside = np.zeros(px.shape, dtype=bool)
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi, xj, yj = x[i], y[i], x[j], y[j]
        cond = ((yi > py) != (yj > py)) & \
               (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi)
        inside ^= cond
        j = i
    return inside


def main(argv=None):
    ap = argparse.ArgumentParser(description="Kandidaten auf OSM-Wald filtern")
    ap.add_argument("geojson", help="Kandidaten-GeoJSON (EPSG:25832)")
    ap.add_argument("--pad-m", type=float, default=100.0,
                    help="Bounding-Box um X m erweitern (Overpass-Abfrage)")
    ap.add_argument("--exclude-roads-m", type=float, default=0.0,
                    help="Kandidaten näher als X m an einem OSM-Weg verwerfen "
                         "(0=aus; empfohlen ~20 – moderne Weg-Anschnitte sind der "
                         "Haupt-Fehlerkandidat)")
    args = ap.parse_args(argv)

    d = json.loads(pathlib.Path(args.geojson).read_text(encoding="utf-8"))
    feats = d["features"]
    if not feats:
        sys.exit("Keine Features in der GeoJSON.")
    px = np.array([f["geometry"]["coordinates"][0] for f in feats], dtype=float)
    py = np.array([f["geometry"]["coordinates"][1] for f in feats], dtype=float)

    # Bounding-Box (UTM -> lat/lon) für Overpass
    pad = args.pad_m
    cx = np.array([px.min() - pad, px.max() + pad])
    cy = np.array([py.min() - pad, py.max() + pad])
    lon, lat = to_lonlat(cx, cy)
    s, w, n, e = lat.min(), lon.min(), lat.max(), lon.max()
    print(f"Overpass-Wald für bbox lat[{s:.4f},{n:.4f}] lon[{w:.4f},{e:.4f}] …")
    osm = fetch_forest(s, w, n, e)
    rings_ll = polygons_from_osm(osm)
    print(f"{len(rings_ll)} Waldpolygone geladen.")
    if not rings_ll:
        sys.exit("Keine Waldpolygone gefunden – Abbruch (nichts gefiltert).")

    # Ringe nach UTM projizieren
    rings = []
    for ring in rings_ll:
        lons = [p[0] for p in ring]; lats = [p[1] for p in ring]
        rx, ry = to_utm(lons, lats)
        rings.append(np.column_stack([rx, ry]))

    in_forest = np.zeros(px.shape, dtype=bool)
    for ring in rings:
        # schnelle bbox-Vorprüfung
        if (ring[:, 0].max() < px.min() or ring[:, 0].min() > px.max() or
                ring[:, 1].max() < py.min() or ring[:, 1].min() > py.max()):
            continue
        in_forest |= point_in_ring(px, py, ring)

    keep_mask = in_forest.copy()

    if args.exclude_roads_m > 0:
        print(f"Wege laden (Ausschluss < {args.exclude_roads_m:.0f} m) …")
        segs = fetch_roads(s, w, n, e)
        if segs:
            slon = np.array([g[0] for g in segs] + [g[2] for g in segs])
            slat = np.array([g[1] for g in segs] + [g[3] for g in segs])
            sx, sy = to_utm(slon, slat)
            n_seg = len(segs)
            ax, ay = sx[:n_seg], sy[:n_seg]
            bx, by = sx[n_seg:], sy[n_seg:]
            print(f"{n_seg} Weg-Segmente.")
            for i in range(len(px)):
                if keep_mask[i] and seg_dist_min(px[i], py[i], ax, ay, bx, by) < args.exclude_roads_m:
                    keep_mask[i] = False

    kept = [f for f, keep in zip(feats, keep_mask) if keep]
    out = {"type": "FeatureCollection",
           "crs": {"type": "name", "properties": {"name": "EPSG:25832"}},
           "features": kept}
    stem = pathlib.Path(args.geojson).stem
    outp = f"{stem}_wald.geojson"
    pathlib.Path(outp).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    n_m = sum(f["properties"].get("type") == "meiler" for f in kept)
    n_p = sum(f["properties"].get("type") == "pinge" for f in kept)
    print(f"\nIm Wald: {len(kept)} von {len(feats)} Kandidaten "
          f"({n_m} Meiler-artig, {n_p} Pingen-artig) -> {outp}")


if __name__ == "__main__":
    main()
