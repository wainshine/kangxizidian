#!/usr/bin/env python3
"""锚点体检 v2：以「2×2 格块」为基准检查锚点框是否切掉笔画/偏离格点。

判据：
  A) 锚点框内墨是否触边（笔画越过框边 = 被切掉）：四边 1px 带内墨量占比；
  B) 锚点框是否落在某个 2×2 格块内且留边合理：anchor_ink_area / block_ink_area；
  C) 整字墨量是否 ≈ 大字量级：anchor_ink / small_ink（小字中位墨量）。
输出 anchors-check.json + 对比图 anchors-check.png（灰=格块，绿=合格锚点，红=可疑，蓝=当前字体框）
"""
import json, os, sys
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from grid_cut_v2 import page_gray, binarize, fit_axis
from validate_anchors import lattice_for

MP = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
FONT = os.path.join(ROOT, "release/KangXiKai-v2.4.15/KangXiKai-Regular-v2.4.15.ttf")
MAN = json.load(open(os.path.join(ROOT, "work/lead/manifest-v2415.json"), encoding="utf-8"))["chars"]


def small_ink_for(gray, ink, half, gutter):
    h, w = gray.shape
    mask = (lambda x, y: x < gutter) if half == "L" else (lambda x, y: x >= gutter)
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, 8)
    areas = []
    for i in range(1, n):
        x, y, ww, hh, a = [int(v) for v in st[i]]
        if not mask(x + ww / 2, y + hh / 2):
            continue
        if 24 <= hh <= 54 and 9 <= ww <= 60 and 40 <= a <= 1200:
            areas.append(a)
    return float(np.median(areas)) if areas else 150.0


def glyph_img(ch, size=140):
    f = ImageFont.truetype(FONT, int(size * 0.8))
    im = Image.new("L", (size, size), 255)
    ImageDraw.Draw(im).text((size // 2, int(size * 0.92)), ch, fill=0, font=f, anchor="ms")
    return im


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
        s_ink = small_ink_for(g, ink, half, gx)
        if lat is None:
            rows.append({**a, "status": "no_lattice"}); continue
        bx = [int(v) for v in a["box"]]
        sub = ink[bx[1]:bx[3], bx[0]:bx[2]]
        if sub.size == 0:
            rows.append({**a, "status": "empty"}); continue
        area = int(sub.sum())
        # 触边：四边 2px 带内墨量占该边长度
        h, w = sub.shape
        edges = {
            "top": float(sub[:2, :].sum()) / max(1, 2 * w),
            "bottom": float(sub[-2:, :].sum()) / max(1, 2 * w),
            "left": float(sub[:, :2].sum()) / max(1, 2 * h),
            "right": float(sub[:, -2:].sum()) / max(1, 2 * h),
        }
        # 期望 2×2 块：锚点中心所在格块
        cx = (bx[0] + bx[2]) / 2.0; cy = (bx[1] + bx[3]) / 2.0
        c = int(round((cx - lat["phx"]) / lat["px"] - 0.5))
        r = int(round((cy - lat["phy"]) / lat["py"] - 0.5))
        block = [int(round(lat["phx"] + c * lat["px"])), int(round(lat["phy"] + r * lat["py"]))]
        block = [block[0], block[1], int(round(block[0] + 2 * lat["px"])), int(round(block[1] + 2 * lat["py"]))]
        bsub = ink[max(0, block[1]):block[3], max(0, block[0]):block[2]]
        block_area = int(bsub.sum())
        ratio_block = area / max(1, block_area)
        ratio_small = area / max(1.0, s_ink)
        cut = max(edges.values()) > 0.10   # 触边墨量高 → 笔画被切
        status = "bad_cut" if cut else ("bad_ratio" if not (2.0 <= ratio_small <= 9.0) else "ok")
        rows.append({**a, "status": status, "edges": {k: round(v, 2) for k, v in edges.items()},
                     "area": area, "small_ink": round(s_ink, 1), "ratio_small": round(ratio_small, 2),
                     "block": block, "ratio_block": round(ratio_block, 2),
                     "lattice": {"px": round(lat["px"], 2), "py": round(lat["py"], 2)}})
    json.dump(rows, open(os.path.join(ROOT, "work/review/anchors-check.json"), "w"),
              ensure_ascii=False, indent=1)
    bad = [r for r in rows if r["status"] in ("bad_cut", "bad_ratio")]
    print(json.dumps({"n": len(rows), "ok": sum(1 for r in rows if r["status"] == "ok"),
                      "bad_cut": sum(1 for r in rows if r["status"] == "bad_cut"),
                      "bad_ratio": sum(1 for r in rows if r["status"] == "bad_ratio"),
                      "bad": [f"{r['char']}:{r['status']}:{r.get('ratio_small')}:{r.get('edges')}" for r in bad]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
