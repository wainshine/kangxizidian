#!/usr/bin/env python3
"""锚点体检 v3（判「笔画被切掉」）：框内墨是否在框外继续（连通性判断，排除邻字）。

对每个锚点：
  取 box 外扩 8px 的裁剪，二值；
  框边带外 2~8px 范围内的墨组件，若与框内墨 8-连通 → 该笔画越过框边（被切）；
  统计被切边（top/bottom/left/right）与程度（越界连通墨量占比）。
同时输出 2×2 格块参考框（灰），用于看锚点是否落在格块内。
输出 anchors-check3.json + anchors-check3.png
"""
import json, os, sys
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from grid_cut_v2 import page_gray, binarize
from validate_anchors import lattice_for

MP = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
FONT = os.path.join(ROOT, "release/KangXiKai-v2.4.15/KangXiKai-Regular-v2.4.15.ttf")
MAN = json.load(open(os.path.join(ROOT, "work/lead/manifest-v2415.json"), encoding="utf-8"))["chars"]


def glyph_img(ch, size=130):
    f = ImageFont.truetype(FONT, int(size * 0.8))
    im = Image.new("L", (size, size), 255)
    ImageDraw.Draw(im).text((size // 2, int(size * 0.92)), ch, fill=0, font=f, anchor="ms")
    return im


def cut_check(ink, box, pad=10):
    x0, y0, x1, y1 = [int(v) for v in box]
    h, w = ink.shape
    X0, Y0 = max(0, x0 - pad), max(0, y0 - pad)
    X1, Y1 = min(w, x1 + pad), min(h, y1 + pad)
    sub = ink[Y0:Y1, X0:X1].copy()
    iy0, ix0 = y0 - Y0, x0 - X0
    iy1, ix1 = iy0 + (y1 - y0), ix0 + (x1 - x0)
    inside = np.zeros_like(sub); inside[iy0:iy1, ix0:ix1] = 1
    # 外扩带 = pad 区域（不含框内）
    ring = (inside == 0)
    n, lab, st, _ = cv2.connectedComponentsWithStats(sub, 8)
    cuts = {"top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0}
    hit = []
    for i in range(1, n):
        comp = (lab == i)
        if not (comp & ring).any() or not (comp & (inside > 0)).any():
            continue  # 只在带外 / 或只在框内
        a = int((comp & ring).sum())
        if a < 6:
            continue
        ys, xs = np.nonzero(comp & ring)
        # 越界方向：相对框边
        sides = set()
        if (ys < iy0).any(): sides.add("top")
        if (ys >= iy1).any(): sides.add("bottom")
        if (xs < ix0).any(): sides.add("left")
        if (xs >= ix1).any(): sides.add("right")
        for s in sides:
            cuts[s] += a
        hit.append((a, sorted(sides)))
    return cuts, hit


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
        cuts, hit = cut_check(ink, a["box"])
        cut_sides = [k for k, v in cuts.items() if v > 0]
        status = "ok" if not cut_sides else "cut"
        block = None
        if lat:
            cx = (a["box"][0] + a["box"][2]) / 2.0; cy = (a["box"][1] + a["box"][3]) / 2.0
            c = int(round((cx - lat["phx"]) / lat["px"] - 0.5)); r = int(round((cy - lat["phy"]) / lat["py"] - 0.5))
            block = [int(round(lat["phx"] + c * lat["px"])), int(round(lat["phy"] + r * lat["py"])),
                     int(round(lat["phx"] + (c + 2) * lat["px"])), int(round(lat["phy"] + (r + 2) * lat["py"]))]
        rows.append({**a, "status": status, "cut_sides": cut_sides, "cuts": {k: int(v) for k, v in cuts.items()},
                     "block": block, "lattice": {"px": lat and round(lat["px"], 2), "py": lat and round(lat["py"], 2)} if lat else None})
    json.dump(rows, open(os.path.join(ROOT, "work/review/anchors-check3.json"), "w"), ensure_ascii=False, indent=1)
    bad = [r for r in rows if r["status"] == "cut"]
    print(json.dumps({"n": len(rows), "ok": len(rows) - len(bad), "cut": len(bad),
                      "cut_list": [f"{r['char']}({r['set']},{r['page']}):{r['cut_sides']}" for r in bad]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
