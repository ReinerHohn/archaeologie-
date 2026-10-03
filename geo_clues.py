#!/usr/bin/env python3
"""Georeferenziertes Wissen (Wikidata/Wikipedia) laden und mit Funden FUSIONIEREN.

'Puzzleteile zusammenlegen': historische Orte aus offenen Wissensbasen (Burgen,
Ruinen, Schanzen, Wüstungen, Klöster, Grabhügel, Bergwerke …) holen und räumlich
gegen unsere LiDAR-Kandidaten matchen. Ein Treffer = Textquelle + Anomalie fallen
zusammen = starker Lead (v.a. Wüstungen: dokumentiert, oft nicht exakt verortet).

Quellen: Wikidata SPARQL (Items mit Koordinaten in der Bounding-Box) + Wikipedia
Geosearch. Alles offen, ohne Key.

Beispiele:
  python3 geo_clues.py --bbox 47.95 7.86 48.05 7.94 --name freiburg
  python3 geo_clues.py --from freiburg_funde.geojson --fuse freiburg_funde.geojson --name freiburg
"""
import argparse
import json
import math
import pathlib
import re
import urllib.parse
import urllib.request

import forest_filter as ff  # to_lonlat / to_utm

UA = {"User-Agent": "archaeologie-research/1.0 (mailto:opmd1988@googlemail.com)"}
WDQS = "https://query.wikidata.org/sparql"
WP = "https://de.wikipedia.org/w/api.php"

# verräterische Begriffe (Label oder Typ) – heritage-relevant.
# \b-Wortgrenzen, sonst matcht 'burg' in 'Freiburg' (und 'turm' in 'Bismarckturm').
KW = re.compile(
    r"\b(Burg|Burgstall|Burgstelle|Schloss|Wasserschloss|Ruine|Schanze|Schanzen|"
    r"Wüstung|Wuestung|Kloster|Kartause|Kapelle|archäolog\w*|archaeolog\w*|"
    r"Hügelgrab|Huegelgrab|Grabhügel|Grabhuegel|Hügelgräber|Tumulus|Grabanlage|"
    r"Ringwall|Wallanlage|Wallburg|befestig\w*|Befestigung|fortification|"
    r"römisch\w*|roemisch\w*|Römer|roman\s|keltisch\w*|Kelten|celtic|Mühle|Muehle|"
    r"Bergwerk|Stollen|Pinge|Motte|Turmhügel|Turmhuegel|Villa\srustica|"
    r"Zisterzienser|Propstei|Letzi|Abschnittsbefestigung|Hochburg|Altschloss)\b", re.I)
# klar NICHT heritage (trotz evtl. Teilmatch)
NEG = re.compile(
    r"Schule|Gymnasium|Hochschul|Bibliothek|Bahnhof|Haltepunkt|Hotel|Sportverein|"
    r"Fußball|Football|Orgel|Naturdenkmal|Mord|Universität|Klinik|Verein|Stützpunkt|"
    r"Kindergarten|Museum|Theater|Stolperstein", re.I)


def sparql_box(s, w, n, e):
    q = (f'SELECT ?item ?itemLabel ?coord ?typeLabel WHERE {{'
         f'  SERVICE wikibase:box {{'
         f'    ?item wdt:P625 ?coord .'
         f'    bd:serviceParam wikibase:cornerSouthWest "Point({w} {s})"^^geo:wktLiteral .'
         f'    bd:serviceParam wikibase:cornerNorthEast "Point({e} {n})"^^geo:wktLiteral .'
         f'  }}'
         f'  OPTIONAL {{ ?item wdt:P31 ?type. }}'
         f'  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "de,en". }}'
         f'}}')
    url = WDQS + "?" + urllib.parse.urlencode({"query": q, "format": "json"})
    r = urllib.request.urlopen(urllib.request.Request(url, headers={**UA, "Accept": "application/sparql-results+json"}), timeout=90).read()
    rows = json.loads(r)["results"]["bindings"]
    items = {}
    for b in rows:
        qid = b["item"]["value"].rsplit("/", 1)[-1]
        label = b.get("itemLabel", {}).get("value", qid)
        typ = b.get("typeLabel", {}).get("value", "")
        m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", b["coord"]["value"])
        if not m:
            continue
        lon, lat = float(m.group(1)), float(m.group(2))
        it = items.setdefault(qid, {"qid": qid, "label": label, "lon": lon, "lat": lat, "types": set()})
        if typ:
            it["types"].add(typ)
    return list(items.values())


def wiki_geosearch(lat, lon, radius_m=5000, limit=50):
    url = WP + "?" + urllib.parse.urlencode({
        "action": "query", "list": "geosearch", "gscoord": f"{lat}|{lon}",
        "gsradius": min(radius_m, 10000), "gslimit": limit, "format": "json"})
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read()
        return [{"label": g["title"], "lat": g["lat"], "lon": g["lon"], "qid": "", "types": set()}
                for g in json.loads(r)["query"]["geosearch"]]
    except Exception:
        return []


def is_heritage(clue):
    text = clue["label"] + " " + " ".join(clue["types"])
    if NEG.search(text):
        return False
    return bool(KW.search(clue["label"]) or any(KW.search(t) for t in clue["types"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Wikidata/Wikipedia-Wissen holen + mit Funden fusionieren")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--bbox", nargs=4, type=float, metavar=("S", "W", "N", "E"), help="lat/lon-Box")
    g.add_argument("--from", dest="from_gj", help="Kandidaten-GeoJSON -> Box daraus ableiten (EPSG:25832)")
    ap.add_argument("--fuse", help="Kandidaten-GeoJSON (EPSG:25832) zum Matchen")
    ap.add_argument("--match-m", type=float, default=250.0, help="Matchradius Hinweis<->Kandidat")
    ap.add_argument("--name", default="region")
    ap.add_argument("--all", action="store_true", help="alle Items (nicht nur heritage)")
    args = ap.parse_args(argv)

    import numpy as np
    if args.bbox:
        s, w, n, e = args.bbox
    else:
        feats = json.loads(pathlib.Path(args.from_gj).read_text(encoding="utf-8"))["features"]
        xs = np.array([f["geometry"]["coordinates"][0] for f in feats])
        ys = np.array([f["geometry"]["coordinates"][1] for f in feats])
        lon, lat = ff.to_lonlat(np.array([xs.min() - 200, xs.max() + 200]),
                                np.array([ys.min() - 200, ys.max() + 200]))
        s, w, n, e = lat.min(), lon.min(), lat.max(), lon.max()
    print(f"Box lat[{s:.4f},{n:.4f}] lon[{w:.4f},{e:.4f}]")

    clues = sparql_box(s, w, n, e)
    print(f"Wikidata: {len(clues)} Items mit Koordinaten")
    wp = wiki_geosearch((s + n) / 2, (w + e) / 2, radius_m=int(max(n - s, e - w) * 111000 / 1.5))
    # Wikipedia-Treffer, die nicht schon als Wikidata-Label da sind
    have = {c["label"] for c in clues}
    clues += [c for c in wp if c["label"] not in have]
    print(f"+ Wikipedia Geosearch: {len(wp)} -> gesamt {len(clues)}")

    if not args.all:
        clues = [c for c in clues if is_heritage(c)]
    print(f"heritage-relevante Hinweise: {len(clues)}")

    # UTM
    if clues:
        cx, cy = ff.to_utm([c["lon"] for c in clues], [c["lat"] for c in clues])
        for c, x, y in zip(clues, cx, cy):
            c["x"], c["y"] = float(x), float(y)

    # Ausgabe GeoJSON
    gj = {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:25832"}},
          "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [c["x"], c["y"]]},
                        "properties": {"label": c["label"], "qid": c["qid"],
                                       "types": ", ".join(sorted(c["types"]))}} for c in clues]}
    pathlib.Path(f"{args.name}_hinweise.geojson").write_text(json.dumps(gj, ensure_ascii=False), encoding="utf-8")

    # Fusion
    matches = []
    if args.fuse and clues:
        cf = json.loads(pathlib.Path(args.fuse).read_text(encoding="utf-8"))["features"]
        fx = np.array([f["geometry"]["coordinates"][0] for f in cf])
        fy = np.array([f["geometry"]["coordinates"][1] for f in cf])
        for c in clues:
            d = np.hypot(fx - c["x"], fy - c["y"])
            i = int(d.argmin())
            if d[i] <= args.match_m:
                p = cf[i]["properties"]
                matches.append((round(float(d[i])), c, p, fx[i], fy[i]))
        matches.sort(key=lambda m: m[0])

    L = [f"# Geo-Hinweise & Puzzle-Matches: {args.name}", "",
         f"{len(clues)} heritage-relevante Orte (Wikidata+Wikipedia) in der Box.", ""]
    L.append("## Hinweise (Textquelle/Wissensbasis)")
    for c in sorted(clues, key=lambda c: c["label"]):
        tp = f" — {', '.join(sorted(c['types']))}" if c["types"] else ""
        wd = f" [{c['qid']}](https://www.wikidata.org/wiki/{c['qid']})" if c["qid"] else ""
        L.append(f"- **{c['label']}**{tp}{wd}  ·  UTM {c['x']:.0f}/{c['y']:.0f}")
    if args.fuse:
        L += ["", f"## 🧩 Puzzle-Matches (Hinweis ≤ {args.match_m:.0f} m an einem Kandidaten): {len(matches)}"]
        for d, c, p, x, y in matches:
            L.append(f"- **{c['label']}** ↔ Kandidat ({p.get('kind', p.get('type',''))}, "
                     f"Score {p.get('score','?')}) · **{d} m** · UTM {x:.0f}/{y:.0f}")
    out = pathlib.Path(f"docs/geo_clues_{args.name}.md")
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"\n-> {out}  und  {args.name}_hinweise.geojson")
    if args.fuse:
        print(f"🧩 {len(matches)} Puzzle-Matches (Hinweis ≤ {args.match_m:.0f} m an Kandidat):")
        for d, c, p, x, y in matches[:15]:
            print(f"  {d:4d} m  {c['label'][:40]:40}  <-> {p.get('kind', p.get('type',''))} @ {x:.0f}/{y:.0f}")


if __name__ == "__main__":
    main()
