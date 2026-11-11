#!/usr/bin/env python3
"""用「大字=2×2 格」规则检查每个锚点框是否合格（严格列距/行距口径）。

对每个锚点：
  拟合该半版的列距 px、行距 py、相位（小字中心，稳健拟合）；
  期望框 = 2×2 格；检查：
    size_ratio_w = w_anchor / (2*px)，size_ratio_h = h_anchor / (2*py)
    offset = 锚点左上角到最近格点节点的距离（单位：格距）
  合格：0.82 ≤ size_ratio ≤ 1.18 且 offset ≤ 0.25 格。
输出 work/review/anchors-valid.json + 一张对比图。
"""
import json, os, sys
import numpy as np, cv2, fitz
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from grid_cut_v2 import page_gray, binarize, fit_axis

MP = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
FONT = os.path.join(ROOT, "release/KangXiKai-v2.4.15/KangXiKai-Regular-v2.4.15.ttf")


def lattice_for(gray, ink, half, gutter):
    h, w = gray.shape
    mask = (lambda x, y: x < gutter) if half == "L" else (lambda x, y: x >= gutter)
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, 8)
    small = []
    for i in range(1, n):
        x, y, ww, hh, a = [int(v) for v in st[i]]
        if not mask(x + ww / 2, y + hh / 2):
            continue
        if 24 <= hh <= 54 and 9 <= ww <= 60 and 40 <= a <= 1200:
            small.append((x + ww / 2, y + hh / 2, hh))
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
            "phy": refine(ys, py, phy), "h0": h0, "n_small": len(small)}


def main():
    anchors = []
    for e in json.load(open(os.path.join(ROOT, "work/font/owner_verified_boxes.json"), encoding="utf-8")):
        anchors.append({"set": "owner", "char": e["char"], "page": e["page"], "half": e.get("half"), "box": e["box"]})
    for line in open(os.path.join(ROOT, "work/font/demo/manifest.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        anchors.append({"set": "demo", "char": r["char"], "page": r["page"], "half": r.get("half"), "box": r["box"]})
    pages = {}
    rows = []
    for a in anchors:
        page = a["page"]
        if page not in pages:
            g = page_gray(page[:2], int(page[3:]))
            ink = binarize(g)
            w = g.shape[1]
            lo, hi = int(w * 0.42), int(w * 0.58)
            gx = int(lo + np.argmin(ink.sum(axis=0)[lo:hi].astype(np.float32)))
            pages[page] = (g, ink, gx)
        g, ink, gx = pages[page]
        half = a["half"] or "L"
        lat = lattice_for(g, ink, half, gx)
        if lat is None:
            rows.append({**a, "ok": None, "reason": "no lattice"}); continue
        bx = a["box"]
        w = bx[2] - bx[0]; h = bx[3] - bx[1]
        rw = w / (2 * lat["px"]); rh = h / (2 * lat["py"])
        # 到最近格点节点偏移
        dx = (bx[0] - lat["phx"]) / lat["px"] - round((bx[0] - lat["phx"]) / lat["px"])
        dy = (bx[1] - lat["phy"]) / lat["py"] - round((bx[1] - lat["phy"]) / lat["py"])
        off = max(abs(dx), abs(dy))
        ok = (0.82 <= rw <= 1.18) and (0.82 <= rh <= 1.18) and off <= 0.25
        rows.append({**a, "ok": bool(ok), "px": round(lat["px"], 2), "py": round(lat["py"], 2),
                     "ratio_w": round(rw, 3), "ratio_h": round(rh, 3), "node_off": round(off, 3)})
    json.dump(rows, open(os.path.join(ROOT, "work/review/anchors-valid.json"), "w"),
              ensure_ascii=False, indent=1)
    bad = [r for r in rows if r["ok"] is False]
    print(json.dumps({"n": len(rows), "ok": sum(1 for r in rows if r["ok"]),
                      "bad": len(bad),
                      "bad_list": [f"{r['char']}({r['set']},{r['page']},{r['ratio_w']},{r['ratio_h']},{r['node_off']})" for r in bad]}))


if __name__ == "__main__":
    main()
