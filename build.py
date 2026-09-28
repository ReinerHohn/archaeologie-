#!/usr/bin/env python3
"""Baut aus methoden/*.json ein self-contained dashboard.html.

Baumuster wie leistungsfaehigkeit/flirt/finanz-wissen:
- reine Python-Standardbibliothek, keine Abhaengigkeiten
- jede Methode ist eine JSON-Karte in methoden/
- Ausgabe ist EINE Datei (dashboard.html) mit eingebetteten Daten, CSS, JS
- Default-Sortierung nach Wirkung / Aufwand (Low-Hanging-Fruits zuerst)

Aufruf:  python3 build.py   ->  schreibt dashboard.html
"""
import html
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
CARDS_DIR = ROOT / "methoden"
OUT = ROOT / "dashboard.html"

# Pflichtfelder je Karte. evidence_level: A=belegt/etabliert, B=vielversprechend, C=explorativ
REQUIRED = {"id", "title", "category", "impact", "effort", "evidence_level", "what"}

CATEGORIES = {
    "geophysik": "⚡ Geophysik (Boden durchleuchten)",
    "fernerkundung": "\U0001f6f0️ Fernerkundung (aus der Luft/All)",
    "ki_texte": "\U0001f916 KI & alte Texte",
    "labor": "\U0001f9ea Labor & Naturwissenschaft",
    "modellierung": "\U0001f5fa️ Modellierung & Daten",
}


def load_cards():
    cards = []
    ids = set()
    for path in sorted(CARDS_DIR.glob("*.json")):
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            sys.exit(f"FEHLER: {path.name} ist kein gueltiges JSON: {exc}")
        missing = REQUIRED - card.keys()
        if missing:
            sys.exit(f"FEHLER: {path.name} fehlen Felder: {sorted(missing)}")
        if card["id"] in ids:
            sys.exit(f"FEHLER: doppelte id '{card['id']}' in {path.name}")
        if card["category"] not in CATEGORIES:
            sys.exit(f"FEHLER: {path.name} unbekannte Kategorie '{card['category']}'")
        ids.add(card["id"])
        card["_score"] = round(card["impact"] / max(card["effort"], 1), 2)
        cards.append(card)
    if not cards:
        sys.exit("Keine Karten in methoden/ gefunden.")
    # Default: Wirkung/Aufwand absteigend, dann Wirkung
    cards.sort(key=lambda c: (c["_score"], c["impact"]), reverse=True)
    return cards


def esc(x):
    return html.escape(str(x))


PAGE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Archaeologie – Methoden fuer neue Funde</title>
<style>
:root {{
  --bg:#12100e; --card:#1f1b16; --card2:#26211a; --ink:#f2ece1; --muted:#a89a86;
  --line:#3a3229; --accent:#d4a24e; --a:#6fbf73; --b:#e0b84c; --c:#c98a5a;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; line-height:1.5; }}
header {{ padding:28px 20px 14px; max-width:1100px; margin:0 auto; }}
h1 {{ margin:0 0 6px; font-size:26px; }}
.sub {{ color:var(--muted); font-size:15px; max-width:70ch; }}
.controls {{ position:sticky; top:0; z-index:5; background:linear-gradient(var(--bg),var(--bg) 80%,transparent);
  padding:12px 20px; max-width:1100px; margin:0 auto; display:flex; flex-wrap:wrap; gap:8px; align-items:center; }}
input[type=search] {{ flex:1; min-width:200px; background:var(--card); border:1px solid var(--line);
  color:var(--ink); padding:9px 12px; border-radius:9px; font-size:15px; }}
select {{ background:var(--card); border:1px solid var(--line); color:var(--ink);
  padding:9px; border-radius:9px; font-size:14px; }}
.chips {{ max-width:1100px; margin:0 auto; padding:0 20px 8px; display:flex; flex-wrap:wrap; gap:6px; }}
.chip {{ cursor:pointer; border:1px solid var(--line); background:var(--card); color:var(--muted);
  padding:5px 11px; border-radius:20px; font-size:13px; user-select:none; }}
.chip.on {{ background:var(--accent); color:#1a1510; border-color:var(--accent); font-weight:600; }}
main {{ max-width:1100px; margin:0 auto; padding:8px 20px 60px;
  display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:14px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px 16px 14px;
  display:flex; flex-direction:column; gap:9px; }}
.card h2 {{ margin:0; font-size:17px; }}
.cat {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
.metrics {{ display:flex; flex-wrap:wrap; gap:6px; font-size:12px; }}
.badge {{ background:var(--card2); border:1px solid var(--line); border-radius:7px; padding:3px 8px; }}
.badge.score {{ background:var(--accent); color:#1a1510; border-color:var(--accent); font-weight:700; }}
.ev-A {{ color:var(--a); }} .ev-B {{ color:var(--b); }} .ev-C {{ color:var(--c); }}
.what {{ font-size:14px; }}
details {{ font-size:13.5px; border-top:1px solid var(--line); padding-top:8px; }}
details summary {{ cursor:pointer; color:var(--accent); font-weight:600; }}
details p {{ margin:8px 0 2px; }}
details .lbl {{ color:var(--muted); font-weight:600; }}
ul {{ margin:4px 0 0; padding-left:18px; }}
.empty {{ grid-column:1/-1; text-align:center; color:var(--muted); padding:40px; }}
footer {{ max-width:1100px; margin:0 auto; padding:0 20px 40px; color:var(--muted); font-size:12.5px; }}
a {{ color:var(--accent); }}
</style>
</head>
<body>
<header>
  <h1>\U0001f3fa Archaeologie – Methoden fuer neue Funde</h1>
  <p class="sub">Ein durchsuchbarer Katalog von Methoden, mit denen man neue archaeologische
  Fundstellen entdeckt: den Boden mit Stromfeldern &amp; Magnetik durchleuchten, aus Luft und
  All scannen, alte Texte und Karten mit KI durchforsten. Sortiert nach
  <b>Wirkung ÷ Aufwand</b> – die groessten Hebel zuerst.</p>
</header>
<div class="controls">
  <input id="q" type="search" placeholder="Suchen (z.B. LiDAR, Widerstand, Keilschrift, Cropmark)…">
  <select id="sort">
    <option value="score">Wirkung ÷ Aufwand</option>
    <option value="impact">nur Wirkung</option>
    <option value="effort">geringster Aufwand</option>
    <option value="evidence">Evidenz (belegt zuerst)</option>
  </select>
</div>
<div class="chips" id="chips"></div>
<main id="grid"></main>
<footer>
  {n} Methoden · Evidenz: <span class="ev-A">A belegt/etabliert</span> ·
  <span class="ev-B">B vielversprechend</span> · <span class="ev-C">C explorativ</span>.
  Wirkung &amp; Aufwand sind grobe Einschaetzungen (1–5) als Priorisierungshilfe, keine harten Werte.
</footer>
<script>
const CARDS = {data};
const CATS = {cats};
const EV = {{A:"belegt", B:"vielversprechend", C:"explorativ"}};
let active = new Set();
const grid = document.getElementById("grid");
const chipsEl = document.getElementById("chips");
const q = document.getElementById("q");
const sortEl = document.getElementById("sort");

Object.entries(CATS).forEach(([key,label]) => {{
  const c = document.createElement("span");
  c.className = "chip"; c.textContent = label; c.dataset.key = key;
  c.onclick = () => {{ c.classList.toggle("on");
    if(active.has(key)) active.delete(key); else active.add(key); render(); }};
  chipsEl.appendChild(c);
}});

function li(arr) {{ return "<ul>" + arr.map(x => "<li>"+x+"</li>").join("") + "</ul>"; }}

function render() {{
  const term = q.value.trim().toLowerCase();
  const mode = sortEl.value;
  let list = CARDS.filter(c => {{
    if(active.size && !active.has(c.category)) return false;
    if(!term) return true;
    return (c._hay).includes(term);
  }});
  const cmp = {{
    score:(a,b)=>b._score-a._score||b.impact-a.impact,
    impact:(a,b)=>b.impact-a.impact,
    effort:(a,b)=>a.effort-b.effort||b.impact-a.impact,
    evidence:(a,b)=>a.evidence_level.localeCompare(b.evidence_level)||b._score-a._score,
  }}[mode];
  list = list.slice().sort(cmp);
  grid.innerHTML = list.length ? "" : '<div class="empty">Nichts gefunden.</div>';
  for(const c of list) {{
    const el = document.createElement("div");
    el.className = "card";
    let extra = "";
    if(c.how_new_finds) extra += '<p><span class="lbl">Wie es neue Funde bringt:</span> '+c.how_new_finds+'</p>';
    if(c.how_to) extra += '<p><span class="lbl">Vorgehen:</span></p>'+li(c.how_to);
    if(c.examples) extra += '<p><span class="lbl">Beispiel-Funde:</span></p>'+li(c.examples);
    if(c.combos) extra += '<p><span class="lbl">Stark kombiniert mit:</span> '+c.combos.join(", ")+'</p>';
    if(c.limits) extra += '<p><span class="lbl">Grenzen/Risiken:</span> '+c.limits+'</p>';
    if(c.cost) extra += '<p><span class="lbl">Kosten/Zugang:</span> '+c.cost+'</p>';
    el.innerHTML =
      '<div class="cat">'+CATS[c.category]+'</div>'+
      '<h2>'+c.title+'</h2>'+
      '<div class="metrics">'+
        '<span class="badge score">Hebel '+c._score+'</span>'+
        '<span class="badge">Wirkung '+c.impact+'/5</span>'+
        '<span class="badge">Aufwand '+c.effort+'/5</span>'+
        '<span class="badge ev-'+c.evidence_level+'">Evidenz '+c.evidence_level+' · '+EV[c.evidence_level]+'</span>'+
      '</div>'+
      '<div class="what">'+c.what+'</div>'+
      (extra ? '<details><summary>Mehr</summary>'+extra+'</details>' : '');
    grid.appendChild(el);
  }}
}}
q.oninput = render; sortEl.onchange = render;
render();
</script>
</body>
</html>
"""


def main():
    cards = load_cards()
    for c in cards:
        hay = " ".join(str(c.get(k, "")) for k in
                       ("title", "what", "how_new_finds", "category")).lower()
        hay += " " + " ".join(map(str, c.get("examples", []))).lower()
        c["_hay"] = hay
    payload = json.dumps(cards, ensure_ascii=False)
    page = PAGE.format(
        data=payload,
        cats=json.dumps(CATEGORIES, ensure_ascii=False),
        n=len(cards),
    )
    OUT.write_text(page, encoding="utf-8")
    print(f"OK: {len(cards)} Methoden -> {OUT.name}")


if __name__ == "__main__":
    main()
