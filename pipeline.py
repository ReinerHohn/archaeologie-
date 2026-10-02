#!/usr/bin/env python3
"""Ein-Kommando-Pipeline: Gebiet -> gerankte, bereinigte LiDAR-Kandidatenliste.

Verkettet die getesteten Einzelwerkzeuge:
  1. fetch_dgm_bw.py   DGM1-Kacheln des LGL BW laden (--center/--tiles)
  2. lidar_prospect.py Meiler-/Pingen-Kandidaten (Bench-Filter fürs Steilgelände)
  3. forest_filter.py  auf Wald begrenzen + moderne Wege ausschließen (OSM)
  4. denkmal_check.py  gegen amtliches Denkmalverzeichnis (LAD BW) markieren
Am Ende: Rangliste der amtlich UNBEKANNTEN Kandidaten (die „Prüfliste").

Beispiele:
  python3 pipeline.py --center 47.995,7.852 --radius-km 3 --out data/freiburg
  python3 pipeline.py --tiles 417,5316 419,5318 --out data/run --skip-fetch
"""
import argparse
import glob
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
PY = sys.executable


def run(cmd):
    print("\n$ " + " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, cwd=HERE)


def main(argv=None):
    ap = argparse.ArgumentParser(description="LiDAR-Prospektions-Pipeline (BW)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--center", help="'lat,lon' (WGS84)")
    g.add_argument("--tiles", nargs="*", help="Kachel-SW-Ecken 'Ost_km,Nord_km'")
    ap.add_argument("--radius-km", type=float, default=3.0)
    ap.add_argument("--out", default="data/run", help="Datenverzeichnis für Kacheln")
    ap.add_argument("--bench-margin", type=float, default=3.0)
    ap.add_argument("--h-pos", type=float, default=0.2)
    ap.add_argument("--exclude-roads-m", type=float, default=20.0)
    ap.add_argument("--radius-m", type=float, default=25.0, help="Denkmal-Trefferradius")
    ap.add_argument("--skip-fetch", action="store_true", help="vorhandene Daten in --out nutzen")
    ap.add_argument("--name", default="region", help="Basisname der Ergebnisdateien")
    args = ap.parse_args(argv)

    outdir = pathlib.Path(args.out)

    # 1. laden
    if not args.skip_fetch:
        fcmd = [PY, "fetch_dgm_bw.py", "--out", str(outdir)]
        if args.center:
            fcmd += ["--center", args.center, "--radius-km", str(args.radius_km)]
        else:
            fcmd += ["--tiles"] + args.tiles
        run(fcmd)

    xyz = sorted(glob.glob(str(outdir / "*.xyz")))
    if not xyz:
        sys.exit(f"Keine XYZ-Dateien in {outdir} – erst laden (ohne --skip-fetch).")

    # 2. detektieren + zusammenführen
    merged = f"{args.name}_kandidaten.geojson"
    run([PY, "lidar_prospect.py", *xyz,
         "--bench-margin", str(args.bench_margin), "--h-pos", str(args.h_pos),
         "--merge", merged])

    # 3. Wald + Wege
    run([PY, "forest_filter.py", merged, "--exclude-roads-m", str(args.exclude_roads_m)])
    wald = f"{args.name}_kandidaten_wald.geojson"

    # 4. Denkmal-Abgleich
    run([PY, "denkmal_check.py", wald, "--radius-m", str(args.radius_m)])
    final = f"{args.name}_kandidaten_wald_denkmalabgleich.geojson"

    # 5. Rangliste der unbekannten Kandidaten
    feats = json.loads(pathlib.Path(final).read_text(encoding="utf-8"))["features"]
    unknown = [f for f in feats if not f["properties"].get("amtlich_bekannt")]
    unknown.sort(key=lambda f: f["properties"]["amplitude_m"], reverse=True)
    print("\n" + "=" * 64)
    print(f"ERGEBNIS: {len(feats)} Kandidaten (Wald & wegfern), "
          f"davon {len(unknown)} amtlich UNBEKANNT")
    print("Top-Prüfliste (amtlich unbekannt, nach Amplitude):")
    print(f"{'Typ':7} {'Ost':>7} {'Nord':>8} {'Amp':>5} {'R':>4}")
    for f in unknown[:20]:
        p = f["properties"]
        x, y = f["geometry"]["coordinates"]
        print(f"{p['type']:7} {x:7.0f} {y:8.0f} {p['amplitude_m']:5.2f} {p['radius_m']:4.1f}")
    print(f"\nDateien: {merged}, {wald}, {final}")
    print("Nächster Schritt: Top-Punkte im Hillshade/Luftbild prüfen, dann Gelände, "
          "dann der Denkmalpflege melden.")


if __name__ == "__main__":
    main()
