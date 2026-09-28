#!/usr/bin/env python3
"""LiDAR-Prospektion: aus DGM1-Kacheln runde Meiler-/Pingen-Kandidaten finden.

Erster Schritt der Sweet-Spot-Pipeline (siehe README): offene DGM1-Daten
(z.B. LGL Baden-Wuerttemberg, opengeodata.lgl-bw.de, Kacheln 2x2 km, GeoTIFF
oder ASCII-XYZ, kostenlos/Datenlizenz Deutschland) einlesen und

  1. ein Local-Relief-Model (LRM = Gelaende minus grossraeumiger Mittelwert)
     sowie ein Hillshade rechnen (Mikrorelief sichtbar machen),
  2. kompakte, rundliche ERHEBUNGEN  -> Koehlerei-Meilerplatten,
     kompakte, rundliche VERTIEFUNGEN -> Bergbau-Pingen,
  als Punktliste (GeoJSON + CSV) ausgeben und optional als PNG markieren.

Das ist ein Kandidaten-Detektor, KEIN Beweis: jeder Treffer gehoert im Gelaende
bzw. mit weiteren Methoden geprueft und der Denkmalpflege gemeldet (nicht graben).

Abhaengigkeiten: numpy (Pflicht); rasterio (fuer GeoTIFF, optional);
Pillow (fuer PNG-Overlay, optional). scipy wird NICHT gebraucht.

Beispiele:
  python3 lidar_prospect.py --demo               # synthetische Kachel, sofort testbar
  python3 lidar_prospect.py kachel_dgm1.tif      # eine GeoTIFF-Kachel
  python3 lidar_prospect.py *.xyz --png          # XYZ-Kacheln + Bildausgabe
"""
import argparse
import csv
import json
import math
import pathlib
import sys

import numpy as np

try:
    import rasterio
    from rasterio.transform import xy as _rio_xy
except Exception:
    rasterio = None

try:
    from PIL import Image, ImageDraw
except Exception:
    Image = None

DEFAULT_CRS = "EPSG:25832"  # UTM32N – ATKIS/LGL Baden-Wuerttemberg


# ----------------------------------------------------------------------------
# numpy-Filter (ohne scipy)
# ----------------------------------------------------------------------------
def box_mean(a, r):
    """Mittelwert ueber (2r+1)x(2r+1)-Fenster via Integralbild, randgeclamped."""
    a = np.asarray(a, dtype=np.float64)
    h, w = a.shape
    ii = np.zeros((h + 1, w + 1), dtype=np.float64)
    ii[1:, 1:] = a.cumsum(0).cumsum(1)
    rows = np.arange(h)
    cols = np.arange(w)
    r0 = np.clip(rows - r, 0, h)
    r1 = np.clip(rows + r + 1, 0, h)
    c0 = np.clip(cols - r, 0, w)
    c1 = np.clip(cols + r + 1, 0, w)
    s = ii[np.ix_(r1, c1)] - ii[np.ix_(r0, c1)] - ii[np.ix_(r1, c0)] + ii[np.ix_(r0, c0)]
    cnt = (r1 - r0)[:, None] * (c1 - c0)[None, :]
    return s / cnt


def max_filter(a, r):
    """Separables Maximum ueber quadratisches (2r+1)-Fenster."""
    out = a.copy()
    for d in range(1, r + 1):
        out[:, :-d] = np.maximum(out[:, :-d], a[:, d:])
        out[:, d:] = np.maximum(out[:, d:], a[:, :-d])
    h = out.copy()
    for d in range(1, r + 1):
        out[:-d, :] = np.maximum(out[:-d, :], h[d:, :])
        out[d:, :] = np.maximum(out[d:, :], h[:-d, :])
    return out


def hillshade(dem, res, az_deg=315.0, alt_deg=45.0):
    dy, dx = np.gradient(dem, res)
    slope = np.arctan(np.hypot(dx, dy))
    aspect = np.arctan2(-dx, dy)
    az = math.radians(360.0 - az_deg + 90.0)
    alt = math.radians(alt_deg)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(hs, 0.0, 1.0)


# ----------------------------------------------------------------------------
# Kachel laden (GeoTIFF via rasterio, oder ASCII-XYZ)
# ----------------------------------------------------------------------------
class Tile:
    """dem[row,col] + Georeferenz. xy(row,col) -> (x,y) in CRS-Einheiten (m)."""

    def __init__(self, dem, res, x0, y_top, crs):
        self.dem = dem            # y_top = Nordrand; Zeilen laufen nach Sueden
        self.res = float(res)
        self.x0 = float(x0)       # x der linken Kachelkante (Spalte 0)
        self.y_top = float(y_top)
        self.crs = crs

    def xy(self, row, col):
        return (self.x0 + (col + 0.5) * self.res,
                self.y_top - (row + 0.5) * self.res)


def load_geotiff(path):
    if rasterio is None:
        sys.exit("FEHLER: GeoTIFF braucht rasterio (pip install rasterio) – "
                 "oder ASCII-XYZ verwenden.")
    with rasterio.open(path) as ds:
        dem = ds.read(1).astype(np.float64)
        nod = ds.nodata
        if nod is not None:
            dem[dem == nod] = np.nan
        t = ds.transform
        res = abs(t.a)
        # Kachel-Nordwest-Ecke
        x0, y_top = _rio_xy(t, 0, 0, offset="ul")
        crs = str(ds.crs) if ds.crs else DEFAULT_CRS
    return Tile(dem, res, x0, y_top, crs)


def load_xyz(path):
    data = np.loadtxt(path)
    if data.ndim != 2 or data.shape[1] < 3:
        sys.exit(f"FEHLER: {path} ist kein XYZ mit 3 Spalten.")
    xs = np.unique(data[:, 0])
    ys = np.unique(data[:, 1])
    res = float(np.median(np.diff(xs))) if len(xs) > 1 else 1.0
    nx, ny = len(xs), len(ys)
    x0, xmaxn = xs.min(), xs.max()
    y0, ymax = ys.min(), ys.max()
    col = np.round((data[:, 0] - x0) / res).astype(int)
    row = np.round((ymax - data[:, 1]) / res).astype(int)  # Zeile 0 = Nord
    dem = np.full((ny, nx), np.nan)
    ok = (row >= 0) & (row < ny) & (col >= 0) & (col < nx)
    dem[row[ok], col[ok]] = data[ok, 2]
    # x0 als linke Kante (Knoten liegt in Zellmitte -> halbe Zelle zurueck)
    return Tile(dem, res, x0 - res / 2.0, ymax + res / 2.0, DEFAULT_CRS)


def load_tile(path):
    p = str(path).lower()
    if p.endswith((".tif", ".tiff")):
        return load_geotiff(path)
    if p.endswith((".xyz", ".txt", ".asc")):
        return load_xyz(path)
    # Versuch GeoTIFF, sonst XYZ
    return load_geotiff(path) if rasterio else load_xyz(path)


def make_demo_tile(res=1.0, n=400, seed=42):
    """Synthetische Kachel: sanfter Hang + Rauschen + 3 Meiler + 2 Pingen."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    dem = 200.0 + 0.03 * xx + 0.01 * yy               # regionaler Hang
    dem += 0.05 * rng.standard_normal((n, n))          # Mikro-Rauschen
    truth = []

    def blob(cx, cy, rad, amp, kind):
        g = amp * np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (rad ** 2))))
        return g, (cx, cy, kind)

    specs = [
        (90, 110, 5.0, 0.45, "meiler"),
        (250, 80, 6.0, 0.35, "meiler"),
        (150, 300, 4.5, 0.50, "meiler"),
        (320, 250, 5.0, -0.55, "pinge"),
        (70, 330, 4.0, -0.40, "pinge"),
    ]
    for cx, cy, rad, amp, kind in specs:
        g, t = blob(cx, cy, rad, amp, kind)
        dem += g
        truth.append(t)
    return Tile(dem, res, 400000.0, 5300000.0, DEFAULT_CRS), truth


# ----------------------------------------------------------------------------
# Detektion
# ----------------------------------------------------------------------------
def slope_deg(dem, res):
    dy, dx = np.gradient(dem, res)
    return np.degrees(np.arctan(np.hypot(dx, dy)))


def detect(tile, bg_m=15.0, smooth_m=2.0, peak_m=4.0,
           h_pos=0.15, h_neg=0.15, r_min_m=2.0, r_max_m=10.0, min_sep_m=6.0,
           amp_max=1.5, flat_deg=12.0, bench_margin=0.0):
    """Findet rundliche Erhebungen (Meiler) und Vertiefungen (Pingen).

    Für echtes (Steil-)Gelände Diskriminatoren, sonst ertrinkt man in
    Bachtälern/Felsen/Hangkanten – oder auf flachen Talböden im Rauschen:
      * amp_max: Amplituden-BAND [h_pos..amp_max] – Meiler/Pingen sind FLACH
        (~0,2–0,8 m), nicht metertiefe Naturformen.
      * flat_deg: der Kandidat muss LOKAL FLACH sein (Meilerplatte = in den Hang
        gebaute ebene Bühne).
      * bench_margin (>0 aktiviert): die UMGEBUNG muss um mind. so viele Grad
        steiler sein als die Platte -> „flache Bühne AUF einem Hang". Schließt
        flache Talböden UND gleichmäßige Steilhänge aus (die echte Meiler-
        Signatur). Für Wald-Hänge ~3° sinnvoll; 0 = aus.
    """
    dem = tile.dem
    res = tile.res
    filled = np.where(np.isnan(dem), np.nanmedian(dem), dem)

    lrm = filled - box_mean(filled, max(1, int(round(bg_m / res))))
    if smooth_m > 0:
        lrm = box_mean(lrm, max(1, int(round(smooth_m / res))))

    # lokale Ebenheit: mittlere Hangneigung im Umkreis des Kandidaten
    slp = slope_deg(filled, res)
    r_max = max(1, int(round(r_max_m / res)))
    flat = box_mean(slp, r_max)
    valid = (~np.isnan(dem)) & (flat <= flat_deg)
    if bench_margin > 0:
        ring = box_mean(slp, 3 * r_max)           # breitere Umgebung
        valid &= (ring - flat) >= bench_margin     # Umgebung deutlich steiler

    rw = max(1, int(round(peak_m / res)))
    r_min = max(1, int(round(r_min_m / res)))
    min_sep = max(1, int(round(min_sep_m / res)))
    # Randstreifen ausblenden: dort ist das LRM-Hintergrundfilter unzuverlaessig
    # (Integralbild-Clamping) -> sonst Fehlalarm-Flut an den Kachelkanten.
    margin = max(1, int(round(bg_m / res)))
    if 2 * margin < min(valid.shape):
        valid[:margin, :] = valid[-margin:, :] = False
        valid[:, :margin] = valid[:, -margin:] = False

    def extract(field, thr, kind):
        loc_max = (field == max_filter(field, rw)) & (field > thr) & valid
        rows, cols = np.where(loc_max)
        cand = []
        for r, c in zip(rows, cols):
            v = float(field[r, c])
            if v > amp_max:                       # zu groß = Naturform (Graben/Fels)
                continue
            rad = _estimate_radius(field, r, c, v, r_max + 2)
            if r_min <= rad <= r_max:
                cand.append((abs(v), r, c, rad, kind))
        return cand

    cand = extract(lrm, h_pos, "meiler")
    cand += extract(-lrm, h_neg, "pinge")

    # Non-Maximum-Suppression: staerkste zuerst, nahe Duplikate verwerfen
    cand.sort(reverse=True)
    kept = []
    for score, r, c, rad, kind in cand:
        if all((r - kr) ** 2 + (c - kc) ** 2 >= min_sep ** 2 for _, kr, kc, _, _ in kept):
            kept.append((score, r, c, rad, kind))

    out = []
    for score, r, c, rad, kind in kept:
        x, y = tile.xy(r, c)
        out.append({
            "type": kind, "x": round(x, 2), "y": round(y, 2),
            "row": int(r), "col": int(c),
            "amplitude_m": round(float(score), 3),
            "radius_m": round(rad * res, 1),
        })
    return out, lrm


def _estimate_radius(field, r, c, v, rmax):
    """Radius: Schritte nach aussen (4 Richtungen), bis Feld < 0.4*v; Mittel."""
    half = 0.4 * v
    h, w = field.shape
    dists = []
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        d = 0
        while d < rmax:
            rr, cc = r + dr * (d + 1), c + dc * (d + 1)
            if not (0 <= rr < h and 0 <= cc < w) or field[rr, cc] < half:
                break
            d += 1
        dists.append(d)
    return max(1.0, float(np.mean(dists)))


# ----------------------------------------------------------------------------
# Ausgabe
# ----------------------------------------------------------------------------
def write_outputs(hits, tile, stem, want_png):
    gj = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": tile.crs}},
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [h["x"], h["y"]]},
            "properties": {k: h[k] for k in ("type", "amplitude_m", "radius_m")},
        } for h in hits],
    }
    gj_path = f"{stem}_kandidaten.geojson"
    csv_path = f"{stem}_kandidaten.csv"
    pathlib.Path(gj_path).write_text(json.dumps(gj, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["type", "x", "y", "amplitude_m", "radius_m", "crs"])
        for h in hits:
            wr.writerow([h["type"], h["x"], h["y"], h["amplitude_m"], h["radius_m"], tile.crs])
    written = [gj_path, csv_path]

    if want_png and Image is not None:
        hs = hillshade(np.where(np.isnan(tile.dem), np.nanmedian(tile.dem), tile.dem), tile.res)
        img = Image.fromarray((hs * 255).astype(np.uint8)).convert("RGB")
        dr = ImageDraw.Draw(img)
        for h in hits:
            col = (60, 200, 90) if h["type"] == "meiler" else (240, 120, 60)
            rr = max(4, int(h["radius_m"] / tile.res))
            x, y = h["col"], h["row"]
            dr.ellipse([x - rr, y - rr, x + rr, y + rr], outline=col, width=2)
        png_path = f"{stem}_hillshade.png"
        img.save(png_path)
        written.append(png_path)
    elif want_png:
        print("  (PNG uebersprungen: Pillow nicht installiert)")
    return written


def process(tile, stem, args):
    hits, _ = detect(tile, bg_m=args.bg, h_pos=args.h_pos, h_neg=args.h_neg,
                     r_min_m=args.r_min, r_max_m=args.r_max, min_sep_m=args.min_sep,
                     amp_max=args.amp_max, flat_deg=args.flat_deg,
                     bench_margin=args.bench_margin)
    n_m = sum(h["type"] == "meiler" for h in hits)
    n_p = sum(h["type"] == "pinge" for h in hits)
    print(f"  {len(hits)} Kandidaten  ({n_m} Meiler-artig, {n_p} Pingen-artig)")
    written = write_outputs(hits, tile, stem, args.png)
    print("  geschrieben: " + ", ".join(written))
    return hits


def build_argparser():
    ap = argparse.ArgumentParser(description="LiDAR-DGM1 -> Meiler-/Pingen-Kandidaten")
    ap.add_argument("tiles", nargs="*", help="DGM1-Kacheln (.tif/.xyz)")
    ap.add_argument("--demo", action="store_true", help="synthetische Testkachel verwenden")
    ap.add_argument("--png", action="store_true", help="Hillshade-PNG mit Markern schreiben")
    ap.add_argument("--bg", type=float, default=15.0, help="LRM-Hintergrundradius (m)")
    ap.add_argument("--h-pos", dest="h_pos", type=float, default=0.15,
                    help="Mindest-Erhebung (m) fuer Meiler")
    ap.add_argument("--h-neg", dest="h_neg", type=float, default=0.15,
                    help="Mindest-Tiefe (m) fuer Pingen")
    ap.add_argument("--r-min", dest="r_min", type=float, default=2.0, help="Min-Radius (m)")
    ap.add_argument("--r-max", dest="r_max", type=float, default=10.0, help="Max-Radius (m)")
    ap.add_argument("--min-sep", dest="min_sep", type=float, default=6.0,
                    help="Mindestabstand zwischen Kandidaten (m)")
    ap.add_argument("--amp-max", dest="amp_max", type=float, default=1.5,
                    help="max. Amplitude (m) – größer = Naturform, verworfen")
    ap.add_argument("--flat-deg", dest="flat_deg", type=float, default=12.0,
                    help="max. lokale Hangneigung (Grad) am Kandidaten")
    ap.add_argument("--bench-margin", dest="bench_margin", type=float, default=0.0,
                    help="Umgebung muss um X Grad steiler sein (Bühne am Hang); 0=aus, Wald~3")
    return ap


def main(argv=None):
    args = build_argparser().parse_args(argv)
    if args.demo:
        tile, _ = make_demo_tile()
        print("DEMO-Kachel (synthetisch, 400x400 m):")
        process(tile, "demo", args)
        return
    if not args.tiles:
        build_argparser().error("Keine Kacheln angegeben (oder --demo).")
    for path in args.tiles:
        print(f"{path}:")
        process(load_tile(path), pathlib.Path(path).stem, args)


if __name__ == "__main__":
    main()
