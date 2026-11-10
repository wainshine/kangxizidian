#!/usr/bin/env python3
"""版面法大字检测：利用「大字笔画粗约为注文2倍」+「大字块=2×2小字格」约束。
1) 背景归一化二值化；2) 每连通域算 p90 笔画厚（距离变换）；
3) 厚笔画域（p90>=阈×小字中位）为种子；4) 种子按距离聚类成字形块；
5) 输出 tight 墨迹 bbox（无 pad，杜绝边角料）。
"""
import json, os, sys
import numpy as np, cv2, fitz

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def page_gray(vol, page, dpi=300):
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
    pix = doc[page - 1].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    g = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    doc.close()
    return g


def detect(gray):
    bg = cv2.medianBlur(gray, 41)
    norm = np.clip(gray.astype(np.int16) - bg.astype(np.int16) + 200, 0, 255).astype(np.uint8)
    thr, _ = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = (norm < min(205, int(thr))).astype(np.uint8)
    # 去斑
    n0, l0, s0, _ = cv2.connectedComponentsWithStats(ink, 8)
    keep = np.zeros_like(ink)
    for i in range(1, n0):
        if s0[i, cv2.CC_STAT_AREA] >= 100:
            keep[l0 == i] = 1
    ink = keep
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, 8)
    comps = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a < 150:
            continue
        m = (lab == i).astype(np.uint8)
        dt = cv2.distanceTransform(m, cv2.DIST_L2, 3)
        v = dt[dt > 0]
        p90 = float(np.percentile(v, 90)) if v.size else 0.0
        comps.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h), "a": int(a),
                      "p90": p90})
    # 小字笔画厚中位（h 在 56-96@300dpi ≈ 28-48@150）
    small = [c for c in comps if 56 <= c["h"] <= 96 and c["a"] < 3000]
    small_p90 = float(np.median([c["p90"] for c in small])) if small else 2.5
    h0 = float(np.median([c["h"] for c in small])) if small else 74.0
    # 厚笔画种子
    seeds = [c for c in comps if c["p90"] >= max(3.4, 1.7 * small_p90) and c["w"] >= 10 and c["h"] >= 8]
    # 聚类：种子 bbox 间距<=26px@300（13px@150）合并
    groups = []
    used = [False] * len(seeds)
    def near(a, b, gap=26):
        return not (a["x"] + a["w"] + gap < b["x"] or b["x"] + b["w"] + gap < a["x"] or
                    a["y"] + a["h"] + gap < b["y"] or b["y"] + b["h"] + gap < a["y"])
    changed = True
    groups = [dict(c) for c in seeds]
    while changed:
        changed = False
        out = []
        used = [False] * len(groups)
        for i in range(len(groups)):
            if used[i]:
                continue
            gi = dict(groups[i])
            for j in range(i + 1, len(groups)):
                if used[j]:
                    continue
                gj = groups[j]
                if near(gi, gj):
                    x0 = min(gi["x"], gj["x"]); y0 = min(gi["y"], gj["y"])
                    x1 = max(gi["x"] + gi["w"], gj["x"] + gj["w"])
                    y1 = max(gi["y"] + gi["h"], gj["y"] + gj["h"])
                    # 块尺寸约束：<= 2.7×h0
                    if (x1 - x0) > 2.7 * h0 or (y1 - y0) > 2.7 * h0:
                        continue
                    gi = {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0,
                          "a": gi.get("a", 0) + gj.get("a", 0),
                          "p90": max(gi.get("p90", 0), gj.get("p90", 0))}
                    used[j] = True; changed = True
            out.append(gi)
        groups = out
    # 扁平横画二次合并（二/三/亖 等多横画大字头）
    flat = [g for g in groups if g["h"] < 0.55 * g["w"]]
    merged = []
    used = [False] * len(groups)
    groups_sorted = sorted(groups, key=lambda g: -g["w"])
    for i, a in enumerate(groups_sorted):
        if used[i]:
            continue
        gi = dict(a)
        for j in range(i + 1, len(groups_sorted)):
            if used[j]:
                continue
            b = groups_sorted[j]
            if not (gi["h"] < 0.55 * gi["w"] and b["h"] < 0.55 * b["w"]):
                continue
            ox = max(0, min(gi["x"] + gi["w"], b["x"] + b["w"]) - max(gi["x"], b["x"]))
            if ox < 0.6 * min(gi["w"], b["w"]):
                continue
            gap = max(gi["y"], b["y"]) - min(gi["y"] + gi["h"], b["y"] + b["h"])
            if gap <= 95:
                x0 = min(gi["x"], b["x"]); y0 = min(gi["y"], b["y"])
                x1 = max(gi["x"] + gi["w"], b["x"] + b["w"]); y1 = max(gi["y"] + gi["h"], b["y"] + b["h"])
                if (y1 - y0) <= 2.7 * h0 and (x1 - x0) <= 2.7 * h0:
                    gi = {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0,
                          "a": gi.get("a", 0) + b.get("a", 0),
                          "p90": max(gi.get("p90", 0), b.get("p90", 0))}
                    used[j] = True
        merged.append(gi)
    groups = merged
    res = []
    for g in groups:
        w150, h150 = g["w"] / 2.0, g["h"] / 2.0
        # 字头类约束：面积≈4小字 ≈ (2*h0/2)^2 附近；尺寸 1.4-2.7×h0@150
        h0_150 = h0 / 2.0
        if not (1.35 * h0_150 <= max(w150, h150) <= 2.75 * h0_150):
            continue
        if min(w150, h150) < 0.55 * h0_150:
            continue
        # 与 4 小字面积比：面积在 [1.2,6]×小字面积中位
        small_area = float(np.median([c["a"] for c in small])) if small else 900.0
        if not (1.0 * small_area <= g["a"] <= 6.5 * small_area):
            continue
        res.append({"box150": [int(round(g["x"] / 2)), int(round(g["y"] / 2)),
                               int(round((g["x"] + g["w"]) / 2)), int(round((g["y"] + g["h"]) / 2))],
                    "p90_150": round(g["p90"] / 2, 2), "ink_area_150": int(g["a"] / 4)})
    return res, {"h0_150": round(h0 / 2, 1), "small_p90_150": round(small_p90 / 2, 2),
                 "n_small": len(small), "n_seeds": len(seeds)}


if __name__ == "__main__":
    vol, page = sys.argv[1], int(sys.argv[2])
    gray = page_gray(vol, page)
    res, meta = detect(gray)
    print(json.dumps({"page": f"{vol}_{page:04d}", "meta": meta, "n": len(res)}, ensure_ascii=False))
    for r in res[:20]:
        print(r)
