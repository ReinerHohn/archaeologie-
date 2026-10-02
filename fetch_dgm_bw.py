#!/usr/bin/env python3
"""Lädt offene DGM1-Kacheln (1 m) des LGL Baden-Württemberg herunter.

Datenquelle (kostenlos, Datenlizenz Deutschland):
  https://opengeodata.lgl-bw.de/  ->  /data/dgm/dgm1_32_<Ost_km>_<Nord_km>_2_bw.zip
Das 2×2-km-Gitter hat UNGERADE Ost-km (…411,413,415,417…) und GERADE Nord-km
(…5314,5316,5318…) als SW-Ecke; jede ZIP (~11 MB) enthält vier 1×1-km-XYZ-Dateien
(EPSG:25832 / UTM32, Höhen NHN). Genau diese XYZ frisst lidar_prospect.py.

Beispiele:
  # nach UTM-Kachel-Ecken (km):
  python3 fetch_dgm_bw.py --tiles 415,5316 417,5316 --out data/freiburg_ost
  # nach Umkreis um Koordinaten (braucht rasterio für lat/lon->UTM):
  python3 fetch_dgm_bw.py --center 47.995,7.852 --radius-km 3 --out data/freiburg
  # nur auflisten/prüfen, nichts laden:
  python3 fetch_dgm_bw.py --center 47.995,7.852 --radius-km 3 --list-only
"""
import argparse
import io
import pathlib
import sys
import urllib.request
import zipfile

ROOT = "https://opengeodata.lgl-bw.de"
UA = {"User-Agent": "Mozilla/5.0 (archaeologie lidar_prospect)"}

# product -> (URL-Pfad, Dateinamen-Präfix, zu entpackende Endungen)
PRODUCTS = {
    "dgm1":   ("/data/dgm",    "dgm1",     (".xyz", ".txt", ".asc")),
    "dgm025": ("/data/dgm025", "dgm025",   (".tif", ".tiff")),
    "dom1":   ("/data/dom1",   "dom1",     (".xyz", ".txt", ".asc", ".tif")),
    "dop20":  ("/data/dop20",  "dop20rgb", (".tif", ".tiff", ".jpg")),
}


def snap_sw(easting_m, northing_m):
    """SW-Ecke der 2-km-Kachel (Ost ungerade km, Nord gerade km)."""
    e_km = int(easting_m // 1000)
    n_km = int(northing_m // 1000)
    e_sw = e_km if e_km % 2 == 1 else e_km - 1   # nächst-kleineres UNGERADES km
    n_sw = n_km if n_km % 2 == 0 else n_km - 1   # nächst-kleineres GERADES km
    return e_sw, n_sw


def tiles_for_bbox(e0, n0, e1, n1):
    e0, e1 = sorted((e0, e1))
    n0, n1 = sorted((n0, n1))
    se, sn = snap_sw(e0, n0)
    ee, en = snap_sw(e1, n1)
    out = []
    e = se
    while e <= ee:
        n = sn
        while n <= en:
            out.append((e, n))
            n += 2
        e += 2
    return out


def latlon_to_utm32(lat, lon):
    try:
        from rasterio.warp import transform
    except Exception:
        sys.exit("FEHLER: --center braucht rasterio (für lat/lon->UTM32). "
                 "Alternativ --tiles mit UTM-km angeben.")
    xs, ys = transform("EPSG:4326", "EPSG:25832", [lon], [lat])
    return xs[0], ys[0]


def tile_name(e_sw, n_sw, product="dgm1"):
    _, prefix, _ = PRODUCTS[product]
    return f"{prefix}_32_{e_sw}_{n_sw}_2_bw.zip"


def tile_url(e_sw, n_sw, product="dgm1"):
    path = PRODUCTS[product][0]
    return f"{ROOT}{path}/{tile_name(e_sw, n_sw, product)}"


def head_ok(url):
    req = urllib.request.Request(url, headers=UA, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200, int(r.headers.get("Content-Length", 0))
    except Exception as e:
        return False, str(e)


def download_and_unzip(e_sw, n_sw, outdir, product="dgm1"):
    url = tile_url(e_sw, n_sw, product)
    exts = PRODUCTS[product][2]
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=300) as r:
        blob = r.read()
    names = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for info in z.infolist():
            if info.filename.lower().endswith(exts):
                target = outdir / pathlib.Path(info.filename).name
                target.write_bytes(z.read(info))
                names.append(target)
    return names


def collect_tiles(args):
    if args.tiles:
        out = []
        for t in args.tiles:
            e, n = t.replace(";", ",").split(",")
            out.append(snap_sw(int(float(e)) * 1000, int(float(n)) * 1000))
        return sorted(set(out))
    if args.bbox_utm:
        e0, n0, e1, n1 = args.bbox_utm
        return tiles_for_bbox(e0, n0, e1, n1)
    if args.center:
        lat, lon = (float(x) for x in args.center.replace(";", ",").split(","))
        e, n = latlon_to_utm32(lat, lon)
        r = args.radius_km * 1000
        return tiles_for_bbox(e - r, n - r, e + r, n + r)
    sys.exit("Bitte --tiles, --bbox-utm oder --center angeben.")


def main(argv=None):
    ap = argparse.ArgumentParser(description="DGM1-Kacheln (LGL BW) herunterladen")
    ap.add_argument("--tiles", nargs="*", help="SW-Ecken als 'Ost_km,Nord_km' (z.B. 415,5316)")
    ap.add_argument("--bbox-utm", nargs=4, type=float, metavar=("E0", "N0", "E1", "N1"),
                    help="Bounding-Box in UTM32-Metern")
    ap.add_argument("--center", help="'lat,lon' (WGS84), z.B. 47.995,7.852")
    ap.add_argument("--radius-km", type=float, default=2.0, help="Radius um --center (km)")
    ap.add_argument("--out", default="data/dgm_bw", help="Zielverzeichnis")
    ap.add_argument("--product", default="dgm1", choices=sorted(PRODUCTS),
                    help="Produkt: dgm1 (1m XYZ), dgm025 (0.25m GeoTIFF), dom1, dop20 (Luftbild)")
    ap.add_argument("--list-only", action="store_true", help="nur URLs prüfen, nicht laden")
    args = ap.parse_args(argv)

    prod = args.product
    tiles = collect_tiles(args)
    print(f"{len(tiles)} Kachel(n) im 2-km-Gitter (Produkt {prod}):")
    outdir = pathlib.Path(args.out)
    if not args.list_only:
        outdir.mkdir(parents=True, exist_ok=True)

    total = []
    for e_sw, n_sw in tiles:
        url = tile_url(e_sw, n_sw, prod)
        if args.list_only:
            ok, info = head_ok(url)
            mb = f"{info/1e6:.1f} MB" if isinstance(info, int) and info else info
            print(f"  [{'OK ' if ok else 'FEHLT'}] {url}  {mb if ok else ''}")
            continue
        try:
            files = download_and_unzip(e_sw, n_sw, outdir, prod)
            total += files
            print(f"  [OK] {tile_name(e_sw, n_sw, prod)} -> {len(files)} Datei(en)")
        except Exception as e:
            print(f"  [FEHLER] {tile_name(e_sw, n_sw, prod)}: {e}")

    if not args.list_only:
        print(f"\n{len(total)} Datei(en) in {outdir}/")


if __name__ == "__main__":
    main()
