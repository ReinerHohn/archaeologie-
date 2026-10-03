#!/usr/bin/env python3
"""Sweet-Spots finden: viele offene Quellen fusionieren -> die LÜCKE aufzeigen.

Strategie für „wo andere noch nichts fanden": ein Ort ist ein Sweet Spot, wenn er
in historischen/wissens-Quellen DOKUMENTIERT ist, aber in KEINEM amtlichen
Denkmalregister steht (und idealerweise von mehreren Quellen genannt wird).
Besonders wertvoll: Wüstungen, Burgställe, Schanzen, Ringwälle, Grabhügel – oft
dokumentiert, aber nie verortet/ergraben.

Fusionierte offene APIs:
  - Wikidata  (SPARQL Box: Items mit Koordinaten + Typen)
  - Wikipedia (Geosearch)
  - OSM/Overpass (historic=* + verräterische Flurnamen)
  - iDAI.gazetteer (Deutsches Archäologisches Institut)
Abgleich: Denkmalregister BW (archäologisch + Bau/Kunst, LAD-WMS).

Beispiel (Breisgau):
  python3 sweet_spots.py --bbox 47.80 7.60 48.15 8.05 --name breisgau
"""
import argparse
import json
import math
import pathlib
import re
import urllib.parse
import urllib.request

import numpy as np

import forest_filter as ff
import geo_clues as gc
import discovery_score as ds
import denkmal_check as dk

UA = {"User-Agent": "archaeologie-research/1.0 (mailto:opmd1988@googlemail.com)"}

# besonders wertvolle (selten erfasste) Typen
PRIORITY = re.compile(
    r"Wüstung|Wuestung|wüst|Burgstall|Burgstelle|Schanze|Ringwall|Abschnittswall|"
    r"Hügelgrab|Huegelgrab|Grabhügel|Grabhuegel|Hügelgräber|Tumulus|Grabanlage|"
    r"Motte|Turmhügel|Turmhuegel|archäolog|archaeolog|Wallanlage|Wallburg|"
    r"römisch|roemisch|keltisch|Bergwerk|Pinge|Letzi|Landwehr|Landgraben", re.I)


def fetch_idai(s, w, n, e, limit=250):
    """iDAI.gazetteer per Polygon-Bbox (lon lat …). Best effort."""
    poly = f"{w} {s} {e} {s} {e} {n} {w} {n} {w} {s}"
    url = ("https://gazetteer.dainst.org/search.json?" +
           urllib.parse.urlencode({"q": "*", "limit": limit,
                                   "polygonFilterCoordinates": poly}))
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
        d = json.loads(r)
        out = []
        for it in d.get("result", []):
            loc = it.get("prefLocation", {}) or {}
            co = loc.get("coordinates")
            if not co:
                continue
            name = (it.get("prefName") or {}).get("title", "")
            types = it.get("types", []) or []
            out.append((co[0], co[1], name, ", ".join(types)))
        return out
    except Exception as ex:
        print("  (iDAI übersprungen:", ex, ")")
        return []


def gather(s, w, n, e):
    """Alle Quellen -> Liste von Orten {lon,lat,label,types,sources}."""
    places = []

    def add(lon, lat, label, types, src):
        places.append({"lon": float(lon), "lat": float(lat), "label": label or "",
                       "types": types or "", "sources": {src}})

    # Wikidata
    try:
        for c in gc.sparql_box(s, w, n, e):
            add(c["lon"], c["lat"], c["label"], ", ".join(sorted(c["types"])), "wikidata")
        print(f"  Wikidata: {sum('wikidata' in p['sources'] for p in places)}")
    except Exception as ex:
        print("  (Wikidata übersprungen:", ex, ")")
    # Wikipedia
    try:
        wp = gc.wiki_geosearch((s + n) / 2, (w + e) / 2,
                               radius_m=int(max(n - s, e - w) * 111000 / 1.5))
        for g in wp:
            add(g["lon"], g["lat"], g["label"], "", "wikipedia")
        print(f"  Wikipedia: {len(wp)}")
    except Exception as ex:
        print("  (Wikipedia übersprungen:", ex, ")")
    # OSM historic + Flurnamen
    try:
        for lon, lat, lab in ds.fetch_hints(s, w, n, e):
            add(lon, lat, lab, "", "osm")
        print(f"  OSM: {sum('osm' in p['sources'] for p in places)}")
    except Exception as ex:
        print("  (OSM übersprungen:", ex, ")")
    # iDAI
    idai = fetch_idai(s, w, n, e)
    for lon, lat, name, types in idai:
        add(lon, lat, name, types, "idai")
    print(f"  iDAI.gazetteer: {len(idai)}")
    return places


def heritage(p):
    text = p["label"] + " " + p["types"]
    if gc.NEG.search(text):
        return False
    return bool(gc.KW.search(p["label"]) or gc.KW.search(p["types"]) or PRIORITY.search(text))


def dedupe(places, merge_m=150.0):
    """Orte in UTM clustern (gleicher Ort aus mehreren Quellen)."""
    xs, ys = ff.to_utm([p["lon"] for p in places], [p["lat"] for p in places])
    for p, x, y in zip(places, xs, ys):
        p["x"], p["y"] = float(x), float(y)
    used = [False] * len(places)
    merged = []
    for i, p in enumerate(places):
        if used[i]:
            continue
        grp = [p]
        used[i] = True
        for j in range(i + 1, len(places)):
            if not used[j] and math.hypot(p["x"] - places[j]["x"], p["y"] - places[j]["y"]) <= merge_m:
                used[j] = True
                grp.append(places[j])
        srcs = set().union(*[g["sources"] for g in grp])
        # bestes Label = längster nicht-leerer
        label = max((g["label"] for g in grp), key=len) if any(g["label"] for g in grp) else ""
        types = ", ".join(sorted({t for g in grp for t in g["types"].split(", ") if t}))
        merged.append({"x": p["x"], "y": p["y"], "lon": p["lon"], "lat": p["lat"],
                       "label": label, "types": types, "sources": sorted(srcs)})
    return merged


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sweet-Spots: dokumentiert aber nicht registriert")
    ap.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("S", "W", "N", "E"))
    ap.add_argument("--name", default="region")
    ap.add_argument("--register-m", type=float, default=80.0, help="Abstand, ab dem 'registriert'")
    args = ap.parse_args(argv)
    s, w, n, e = args.bbox
    print(f"Box lat[{s},{n}] lon[{w},{e}] – Quellen sammeln …")

    places = [p for p in gather(s, w, n, e) if heritage(p)]
    print(f"heritage-relevant: {len(places)}")
    places = dedupe(places)
    print(f"nach Dedupe: {len(places)} Orte")
    if not places:
        return
    px = np.array([p["x"] for p in places]); py = np.array([p["y"] for p in places])

    # Register (beide Layer) als Raster
    registered = np.zeros(len(places), bool)
    try:
        minx, maxx, miny, maxy = px.min() - 200, px.max() + 200, py.min() - 200, py.max() + 200
        wpx = max(1, int((maxx - minx) / 3)); hpx = max(1, int((maxy - miny) / 3))
        if max(wpx, hpx) > 4000:
            sc = 4000 / max(wpx, hpx); wpx, hpx = int(wpx * sc), int(hpx * sc)
        mask = dk.wms_getmap(dk.LYR_DENK, minx, miny, maxx, maxy, wpx, hpx)
        try:
            mask = mask | dk.wms_getmap(dk.LYR_BK, minx, miny, maxx, maxy, wpx, hpx, base=dk.WMS_BK)
        except Exception:
            pass
        rr = args.register_m / ((maxx - minx) / wpx)
        for i in range(len(places)):
            col = (px[i] - minx) / (maxx - minx) * wpx
            row = (maxy - py[i]) / (maxy - miny) * hpx
            c0, c1 = int(max(0, col - rr)), int(min(wpx, col + rr + 1))
            r0, r1 = int(max(0, row - rr)), int(min(hpx, row + rr + 1))
            registered[i] = bool(mask[r0:r1, c0:c1].any())
        print(f"  im Register (≤{args.register_m:.0f} m): {registered.sum()}/{len(places)}")
    except Exception as ex:
        print("  (Register übersprungen:", ex, ")")

    for i, p in enumerate(places):
        p["registered"] = bool(registered[i])
        p["priority"] = bool(PRIORITY.search(p["label"] + " " + p["types"]))
        p["score"] = (3 if p["priority"] else 0) + len(p["sources"]) + (0 if p["registered"] else 2)

    # Sweet Spots = NICHT registriert, nach Score
    spots = sorted([p for p in places if not p["registered"]], key=lambda p: -p["score"])

    gj = {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:25832"}},
          "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [p["x"], p["y"]]},
                        "properties": {k: p[k] for k in ("label", "types", "sources", "priority", "score")}}
                       for p in spots]}
    pathlib.Path(f"{args.name}_sweetspots.geojson").write_text(json.dumps(gj, ensure_ascii=False), encoding="utf-8")

    L = [f"# Sweet-Spots {args.name}: dokumentiert, aber NICHT im Register", "",
         f"{len(spots)} Orte (von {len(places)} dokumentierten) stehen in keinem amtlichen "
         f"Register – priorisiert nach Typ (Wüstung/Burgstall/Schanze…) & Quellenzahl.", ""]
    L.append(f"{'Score':>5} {'Prio':>4}  {'Ost':>7} {'Nord':>8}  Quellen        Label / Typ")
    for p in spots[:40]:
        pr = "★" if p["priority"] else " "
        L.append(f"{p['score']:>5} {pr:>4}  {p['x']:7.0f} {p['y']:8.0f}  "
                 f"{'+'.join(p['sources']):14} {p['label'] or '(ohne Name)'} — {p['types'][:40]}")
    out = pathlib.Path(f"docs/sweetspots_{args.name}.md")
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")

    print(f"\n{len(spots)} SWEET SPOTS (dokumentiert, nicht registriert) -> {out}")
    print(f"{'Score':>5} {'Ost':>7} {'Nord':>8}  Quellen        Label")
    for p in spots[:15]:
        pr = "★" if p["priority"] else " "
        print(f"{p['score']:>5}{pr} {p['x']:7.0f} {p['y']:8.0f}  {'+'.join(p['sources']):14} {p['label'][:34]}")


if __name__ == "__main__":
    main()
