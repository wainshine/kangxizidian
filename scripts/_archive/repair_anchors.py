#!/usr/bin/env python3
"""锚点修复：对被切边的框逐边外扩，直到笔画不再越界（并给出修复后框）。"""
import json, os, sys
import numpy as np, cv2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from grid_cut_v2 import page_gray, binarize
from validate_anchors3 import cut_check

MAX_EXPAND = 26


def repair(ink, box):
    b = [int(v) for v in box]
    history = []
    for _ in range(8):
        cuts, _ = cut_check(ink, b)
        sides = [k for k, v in cuts.items() if v > 0]
        if not sides:
            return b, history
        changed = False
        if "top" in sides and b[1] - 2 >= 0:
            b[1] -= 2; changed = True
        if "bottom" in sides and b[3] + 2 < ink.shape[0]:
            b[3] += 2; changed = True
        if "left" in sides and b[0] - 2 >= 0:
            b[0] -= 2; changed = True
        if "right" in sides and b[2] + 2 < ink.shape[1]:
            b[2] += 2; changed = True
        history.append((sides, b[:]))
        if not changed:
            break
        if (b[0] <= int(box[0]) - MAX_EXPAND and b[1] <= int(box[1]) - MAX_EXPAND and
                b[2] >= int(box[2]) + MAX_EXPAND and b[3] >= int(box[3]) + MAX_EXPAND):
            break
    return b, history


def main():
    rows = json.load(open(os.path.join(ROOT, "work/review/anchors-check3.json"), encoding="utf-8"))
    pages = {}
    out = []
    for r in rows:
        page = r["page"]
        if page not in pages:
            g = page_gray(page[:2], int(page[3:]))
            ink = binarize(g)
            pages[page] = (g, ink)
        g, ink = pages[page]
        nb, hist = repair(ink, r["box"])
        cuts, _ = cut_check(ink, nb)
        out.append({**r, "repaired_box": nb,
                    "repaired_ok": not any(v > 0 for v in cuts.values()),
                    "expanded": [nb[i] - r["box"][i] for i in range(4)]})
    json.dump(out, open(os.path.join(ROOT, "work/review/anchors-repaired.json"), "w"),
              ensure_ascii=False, indent=1)
    repaired = [r for r in out if r["status"] == "cut"]
    print(json.dumps({"n": len(out), "cut_n": len(repaired),
                      "repaired_ok": sum(1 for r in repaired if r["repaired_ok"]),
                      "list": [f"{r['char']}({r['page']}):{r['box']}->{r['repaired_box']}" for r in repaired]}))


if __name__ == "__main__":
    main()
