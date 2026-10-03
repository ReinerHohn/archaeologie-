#!/usr/bin/env python3
"""Test: Merkmals-Klassifikator hebt die Precision auf ungesehener Szene."""
import sys
import numpy as np
import classify_candidates as C
import validate as V

failed = []


def check(name, cond):
    print(("ok  " if cond else "FAIL") + "  " + name)
    if not cond:
        failed.append(name)


tr, gt_tr = V.make_labeled_demo(seed=7)
te, gt_te = V.make_labeled_demo(seed=21)
Xtr, ytr, _ = C.candidates_with_labels(tr, gt_tr)
Xte, yte, xyte = C.candidates_with_labels(te, gt_te)
check("Trainingsszene hat positive + negative", 0 < ytr.sum() < len(ytr))

model = C.fit_logreg(Xtr, ytr)
base = V.match(xyte, gt_te, 15.0)
prob = C.predict(model, Xte)
keep = [xyte[i] for i in range(len(xyte)) if prob[i] >= 0.5]
after = V.match(keep, gt_te, 15.0)

check("Precision steigt deutlich (>= +0.3)", after["precision"] - base["precision"] >= 0.3)
check("Recall bleibt hoch (>= 0.9)", after["recall"] >= 0.9)
check("F1 steigt", after["f1"] > base["f1"])
check("weniger False Positives", after["fp"] < base["fp"])

# Feature-Länge konsistent
check("Feature-Vektor hat erwartete Länge", Xte.shape[1] == len(C.FEATS))

print()
if failed:
    print(f"{len(failed)} Test(s) FEHLGESCHLAGEN: {failed}")
    sys.exit(1)
print("Alle Tests grün.")
