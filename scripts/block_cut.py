#!/usr/bin/env python3
"""2×2 格块切分（源头修复 v3）：格点节点=小字中心；块 = 2×2 格（半格偏移修正）。

约定：小字中心 = 格点节点 (phx + c*px, phy + r*py)；
      2×2 块（左上格 = (c,r)）= [phx+(c-1/2)px, phy+(r-1/2)py, +2px, +2py]。
对给定 (page, half, 现有框)：取框中心 → 最近块；返回块框。
"""
import json, os, sys
import numpy as np, cv2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from grid_cut_v2 import page_gray, binarize, fit_axis


def lattice_for_page(page, half):
    g = page_gray(page[:2], int(page[3:]))
    ink = binarize(g)
    w = g.shape[1]
    lo, hi = int(w * 0.42), int(w * 0.58)
    gx = int(lo + np.argmin(ink.sum(axis=0)[lo:hi].astype(np.float32)))
    h, ww = g.shape
    mask = (lambda x, y: x < gx) if half == "L" else (lambda x, y: x >= gx)
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, 8)
    small = []
    for i in range(1, n):
        x, y, w2, h2, a = [int(v) for v in st[i]]
        if not mask(x + w2 / 2, y + h2 / 2):
            continue
        if 24 <= h2 <= 54 and 9 <= w2 <= 60 and 40 <= a <= 1200:
            small.append((x + w2 / 2, y + h2 / 2, h2))
    if len(small) < 80:
        return None
    h0 = float(np.median([s[2] for s in small]))
    xs = np.array([s[0] for s in small]); ys = np.array([s[1] for s in small])
    sx, px, phx = fit_axis(xs, 0.9 * h0, 1.9 * h0)
    sy, py, phy = fit_axis(ys, 0.85 * h0, 1.6 * h0)
    def refine(vals, pitch, phase):
        lag = np.mod(vals - phase + pitch / 2, pitch) - pitch / 2
        return phase + float(np.median(lag))
    return {"px": float(px), "py": float(py), "phx": refine(xs, px, phx),
            "phy": refine(ys, py, phy), "ink": ink, "gray": g, "gx": gx}


def block_for_box(lat, box):
    px, py = lat["px"], lat["py"]
    cx = (box[0] + box[2]) / 2.0; cy = (box[1] + box[3]) / 2.0
    c = int(round((cx - lat["phx"]) / px - 0.5))
    r = int(round((cy - lat["phy"]) / py - 0.5))
    x0 = int(round(lat["phx"] + (c - 0.5) * px))
    y0 = int(round(lat["phy"] + (r - 0.5) * py))
    x1 = int(round(lat["phx"] + (c + 1.5) * px))
    y1 = int(round(lat["phy"] + (r + 1.5) * py))
    return [x0, y0, x1, y1], (r, c)


def validate_anchors():
    rows = json.load(open(os.path.join(ROOT, "work/review/anchors-repaired.json"), encoding="utf-8"))
    lat_cache = {}
    out = []
    for a in rows:
        key = (a["page"], a["half"] or "L")
        if key not in lat_cache:
            lat_cache[key] = lattice_for_page(a["page"], key[1])
        lat = lat_cache[key]
        if lat is None:
            out.append({**a, "block": None}); continue
        box = a.get("repaired_box") or a["box"]
        blk, cell = block_for_box(lat, box)
        ink = lat["ink"]
        sub = ink[max(0, blk[1]):blk[3], max(0, blk[0]):blk[2]]
        ys, xs = np.nonzero(sub)
        if len(xs):
            ink_bb = [blk[0] + int(xs.min()), blk[1] + int(ys.min()), blk[0] + int(xs.max()), blk[1] + int(ys.max())]
            contained = (ink_bb[0] >= blk[0] and ink_bb[1] >= blk[1] and ink_bb[2] <= blk[2] and ink_bb[3] <= blk[3])
            margins = [ink_bb[0] - blk[0], ink_bb[1] - blk[1], blk[2] - ink_bb[2], blk[3] - ink_bb[3]]
        else:
            contained = False; ink_bb = None; margins = None
        out.append({**a, "block": blk, "cell": cell, "ink_bb": ink_bb,
                    "contained": bool(contained), "margins": margins,
                    "block_size": [blk[2] - blk[0], blk[3] - blk[1]],
                    "lattice": {"px": round(lat["px"], 2), "py": round(lat["py"], 2)}})
    json.dump(out, open(os.path.join(ROOT, "work/review/anchors-blocks.json"), "w"), ensure_ascii=False, indent=1)
    ok = sum(1 for r in out if r.get("contained"))
    print(json.dumps({"n": len(out), "contained": ok,
                      "not_contained": [f"{r['char']}({r['page']})" for r in out if not r.get("contained")]}))


if __name__ == "__main__":
    validate_anchors()
