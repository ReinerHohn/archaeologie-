#!/usr/bin/env python3
"""Durchforstet wissenschaftliche Literatur (OpenAlex) – Methoden & Datensätze.

Zweck: Puzzleteil „Stand der Forschung" + gezielt nach OFFENEN GROUND-TRUTH-
Datensätzen suchen (z.B. kartierte Meilerplätze), die unseren Detektor messbar
kalibrierbar machen. OpenAlex ist frei, ohne Key (höfliche Mail im User-Agent).

Ausgabe: docs/literatur_<slug>.md (Rangliste: Titel, Jahr, Autoren, Typ, DOI,
Open-Access-PDF, Kurz-Abstract) + .json.

Beispiele:
  python3 literature_mine.py "LiDAR Meilerplatz charcoal hearth Schwarzwald"
  python3 literature_mine.py "charcoal hearth dataset LiDAR" --datasets
"""
import argparse
import json
import pathlib
import re
import urllib.parse
import urllib.request

API = "https://api.openalex.org/works"
UA = {"User-Agent": "archaeologie-research/1.0 (mailto:opmd1988@googlemail.com)"}


def reconstruct_abstract(inv):
    if not inv:
        return ""
    pos = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))[:400]


def fetch(query, rows=30, datasets=False):
    params = {"search": query, "per-page": min(rows, 50),
              "sort": "relevance_score:desc",
              "select": "id,title,publication_year,type,doi,authorships,"
                        "primary_location,open_access,abstract_inverted_index,"
                        "cited_by_count"}
    if datasets:
        params["filter"] = "type:dataset"
    url = API + "?" + urllib.parse.urlencode(params)
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
    return json.loads(r).get("results", [])


def row(w):
    auth = [a["author"]["display_name"] for a in w.get("authorships", [])[:3]]
    src = (w.get("primary_location") or {}).get("source") or {}
    return {
        "title": w.get("title") or "(ohne Titel)",
        "year": w.get("publication_year"),
        "type": w.get("type"),
        "authors": auth + (["et al."] if len(w.get("authorships", [])) > 3 else []),
        "venue": src.get("display_name") or "",
        "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
        "oa_pdf": (w.get("open_access") or {}).get("oa_url") or "",
        "cited": w.get("cited_by_count", 0),
        "abstract": reconstruct_abstract(w.get("abstract_inverted_index")),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Literatur/Datensätze via OpenAlex")
    ap.add_argument("query", help="Suchbegriff(e)")
    ap.add_argument("--rows", type=int, default=30)
    ap.add_argument("--datasets", action="store_true", help="nur Datensätze (type:dataset)")
    ap.add_argument("--out", default=None, help="Markdown-Pfad (Default docs/literatur_<slug>.md)")
    args = ap.parse_args(argv)

    works = [row(w) for w in fetch(args.query, args.rows, args.datasets)]
    # Datensätze/offene PDFs nach oben
    works.sort(key=lambda w: (w["type"] != "dataset", not w["oa_pdf"], -(w["cited"] or 0)))

    slug = re.sub(r"[^a-z0-9]+", "-", args.query.lower()).strip("-")[:40]
    out = pathlib.Path(args.out or f"docs/literatur_{slug}.md")
    out.parent.mkdir(exist_ok=True)
    L = [f"# Literatur-Recherche: {args.query}", "",
         f"Quelle: OpenAlex · {len(works)} Treffer · "
         f"{'nur Datensätze' if args.datasets else 'Werke'} · nach Relevanz/Datensatz/Open-Access.",
         ""]
    n_ds = sum(w["type"] == "dataset" for w in works)
    n_oa = sum(bool(w["oa_pdf"]) for w in works)
    L.append(f"**{n_ds} Datensätze, {n_oa} mit Open-Access-PDF.**\n")
    for i, w in enumerate(works, 1):
        tag = " 📊DATENSATZ" if w["type"] == "dataset" else ""
        pdf = f" · [PDF]({w['oa_pdf']})" if w["oa_pdf"] else ""
        doi = f" · doi:{w['doi']}" if w["doi"] else ""
        L.append(f"## {i}. {w['title']} ({w['year']}){tag}")
        L.append(f"{', '.join(w['authors'])} — *{w['venue']}* · {w['cited']}× zitiert{doi}{pdf}")
        if w["abstract"]:
            L.append(f"\n> {w['abstract']}")
        L.append("")
    out.write_text("\n".join(L), encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(works, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{len(works)} Treffer ({n_ds} Datensätze, {n_oa} OA-PDF) -> {out}")
    for w in works[:8]:
        tag = "[DATENSATZ] " if w["type"] == "dataset" else ""
        print(f"  {tag}{w['year']} {w['title'][:72]}")


if __name__ == "__main__":
    main()
