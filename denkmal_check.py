#!/usr/bin/env python3
"""Gleicht LiDAR-Kandidaten mit dem AMTLICHEN Denkmalverzeichnis ab (LAD BW).

Beantwortet die Frage: „Was davon ist längst bekannt?" – gegen den offenen
WMS des Landesamts für Denkmalpflege Baden-Württemberg (archäologische
Kulturdenkmale + Grabungsschutzgebiete):
  https://owsproxy.lgl-bw.de/owsproxy/ows/WMS_LAD_Archaeologische_Kulturdenkmale_BW

Vorgehen: Denkmal-Layer als transparentes PNG über die Kandidaten-Bounding-Box
rendern (GetMap, EPSG:25832), je Kandidat prüfen, ob innerhalb --radius-m eine
Denkmalfläche liegt; für Treffer den Klartext (GetFeatureInfo) holen.

Ausgabe: <name>_denkmalabgleich.geojson mit properties
  amtlich_bekannt (bool), denkmal_info (Text bei Treffer).
Braucht: numpy, Pillow, rasterio (nur falls Reprojektion nötig – hier nicht).
Beispiel:
  python3 denkmal_check.py freiburg_region_kandidaten.geojson --radius-m 25
"""
import argparse
import json
import pathlib
import sys
import urllib.parse
import urllib.request

import numpy as np
from PIL import Image
import io

WMS = "https://owsproxy.lgl-bw.de/owsproxy/ows/WMS_LAD_Archaeologische_Kulturdenkmale_BW"
# Bau- & Kunstdenkmale (stehende Denkmale wie Burgruinen) – zweiter Layer, da
# archäologisches Register z.B. die Kyburg NICHT führt.
WMS_BK = "https://owsproxy.lgl-bw.de/owsproxy/ows/WMS_LAD_Kulturdenkmale_Bau_Kunstdenkmalpflege"
UA = {"User-Agent": "archaeologie-lidar/1.0 (research; monument cross-check)"}
LYR_DENK = "v_archaeologie_kulturdenkmale"
LYR_GSG = "v_archaeologie_grabungsschutzgebiete"
LYR_BK = "v_bau_kunstdenkmalpflege_kulturdenkmale"


def wms_getmap(layer, minx, miny, maxx, maxy, w, h, base=WMS):
    p = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
         "LAYERS": layer, "STYLES": "", "CRS": "EPSG:25832",
         "BBOX": f"{minx},{miny},{maxx},{maxy}", "WIDTH": w, "HEIGHT": h,
         "FORMAT": "image/png", "TRANSPARENT": "TRUE"}
    url = base + "?" + urllib.parse.urlencode(p)
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read()
    if r[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("WMS lieferte kein PNG: " + r[:200].decode("utf-8", "replace"))
    return np.array(Image.open(io.BytesIO(r)).convert("RGBA"))[:, :, 3] > 0


def wms_featureinfo(layer, x, y, half=40):
    p = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetFeatureInfo",
         "LAYERS": layer, "QUERY_LAYERS": layer, "CRS": "EPSG:25832",
         "BBOX": f"{x-half},{y-half},{x+half},{y+half}", "WIDTH": 81, "HEIGHT": 81,
         "I": 40, "J": 40, "FORMAT": "image/png",
         "INFO_FORMAT": "application/json", "FEATURE_COUNT": 5}
    url = WMS + "?" + urllib.parse.urlencode(p)
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read()
        feats = json.loads(r).get("features", [])
        out = []
        for f in feats:
            pr = f.get("properties", {})
            txt = pr.get("info") or pr.get("name") or json.dumps(pr, ensure_ascii=False)
            out.append(" ".join(str(txt).split())[:300])
        return out
    except Exception as e:
        return [f"(FeatureInfo-Fehler: {e})"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Kandidaten gegen amtliches Denkmalverzeichnis (LAD BW)")
    ap.add_argument("geojson", help="Kandidaten-GeoJSON (EPSG:25832)")
    ap.add_argument("--radius-m", type=float, default=25.0, help="Trefferradius zum Denkmal")
    ap.add_argument("--res-m", type=float, default=2.0, help="Rasterauflösung des WMS-Abrufs (m/px)")
    ap.add_argument("--pad-m", type=float, default=100.0, help="Bounding-Box-Puffer")
    args = ap.parse_args(argv)

    feats = json.loads(pathlib.Path(args.geojson).read_text(encoding="utf-8"))["features"]
    if not feats:
        sys.exit("Keine Features.")
    px = np.array([f["geometry"]["coordinates"][0] for f in feats])
    py = np.array([f["geometry"]["coordinates"][1] for f in feats])
    minx, maxx = px.min() - args.pad_m, px.max() + args.pad_m
    miny, maxy = py.min() - args.pad_m, py.max() + args.pad_m
    w = max(1, int(round((maxx - minx) / args.res_m)))
    h = max(1, int(round((maxy - miny) / args.res_m)))
    if max(w, h) > 4000:
        sc = 4000 / max(w, h)
        w, h = int(w * sc), int(h * sc)
    print(f"WMS GetMap {w}x{h} px über bbox …")
    denk = wms_getmap(LYR_DENK, minx, miny, maxx, maxy, w, h)
    try:  # Bau-/Kunstdenkmale dazunehmen (stehende Denkmale, z.B. Burgruinen)
        denk = denk | wms_getmap(LYR_BK, minx, miny, maxx, maxy, w, h, base=WMS_BK)
    except Exception as ex:
        print("  (Bau-/Kunstdenkmal-Layer übersprungen:", ex, ")")
    try:
        gsg = wms_getmap(LYR_GSG, minx, miny, maxx, maxy, w, h)
    except Exception:
        gsg = np.zeros_like(denk)
    print(f"Denkmal-Pixel (arch.+Bau/Kunst): {int(denk.sum())} | Grabungsschutz-Pixel: {int(gsg.sum())}")

    rpx = args.radius_m / ((maxx - minx) / w)

    def hit(mask, x, y):
        col = (x - minx) / (maxx - minx) * w
        row = (maxy - y) / (maxy - miny) * h
        c0, c1 = int(max(0, col - rpx)), int(min(w, col + rpx + 1))
        r0, r1 = int(max(0, row - rpx)), int(min(h, row + rpx + 1))
        return bool(mask[r0:r1, c0:c1].any())

    n_known = 0
    for f, x, y in zip(feats, px, py):
        known = hit(denk, x, y)
        in_gsg = hit(gsg, x, y)
        f["properties"]["amtlich_bekannt"] = known
        f["properties"]["in_grabungsschutzgebiet"] = in_gsg
        if known:
            n_known += 1
            info = wms_featureinfo(LYR_DENK, x, y, half=int(args.radius_m) + 20)
            f["properties"]["denkmal_info"] = info[0] if info else ""

    out = {"type": "FeatureCollection",
           "crs": {"type": "name", "properties": {"name": "EPSG:25832"}},
           "features": feats}
    stem = pathlib.Path(args.geojson).stem
    outp = f"{stem}_denkmalabgleich.geojson"
    pathlib.Path(outp).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    n = len(feats)
    print(f"\nAmtlich bekannt (≤{args.radius_m:.0f} m): {n_known}/{n} ({100*n_known/n:.0f}%)")
    print(f"NICHT im Verzeichnis (potenziell neu ODER Fehlalarm): {n-n_known}/{n}")
    print(f"-> {outp}  (property 'amtlich_bekannt' + 'denkmal_info')")
    known_types = [f["properties"].get("denkmal_info", "")[:80] for f in feats
                   if f["properties"].get("amtlich_bekannt")]
    for t in dict.fromkeys(known_types):
        if t:
            print("   bekannt:", t)


if __name__ == "__main__":
    main()
