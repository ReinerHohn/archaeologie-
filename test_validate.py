#!/usr/bin/env python3
"""Tests für den Validierungs-Harnisch (match-Metrik + Demo-Sweep)."""
import sys
import validate as V

failed = []


def check(name, cond):
    print(("ok  " if cond else "FAIL") + "  " + name)
    if not cond:
        failed.append(name)


# --- match(): bekannter TP/FP/FN-Fall ---
truth = [(0, 0), (100, 0)]
cand = [(1, 0), (2, 0), (100, 1), (500, 500)]   # TP, FP(dup), TP, FP
m = V.match(cand, truth, max_m=10)
check("TP=2", m["tp"] == 2)
check("FP=2", m["fp"] == 2)
check("FN=0", m["fn"] == 0)
check("Recall=1.0", m["recall"] == 1.0)
check("Precision=0.5", m["precision"] == 0.5)

# leere Fälle
check("keine Kandidaten -> recall 0", V.match([], truth, 10)["recall"] == 0.0)

# --- Demo-Sweep: findet die echten Meiler (Recall hoch bei kleiner Schwelle) ---
tile, gt = V.make_labeled_demo()
check("12 synthetische Meiler", len(gt) == 12)
cand = V.detect_xy(tile, h_pos=0.15, bench=0.0)
m = V.match(cand, gt, max_m=15)
check("Recall >= 0.9 bei h_pos 0.15/bench 0", m["recall"] >= 0.9)

print()
if failed:
    print(f"{len(failed)} Test(s) FEHLGESCHLAGEN: {failed}")
    sys.exit(1)
print("Alle Tests grün.")
