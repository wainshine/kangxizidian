#!/usr/bin/env python3
"""三路二值化并集 + 版面几何验证的大字检测（v2.4.6 用）。

二值化：① 背景归一化+Otsu ② 相对对比度 ③ Sauvola
每路取「大字尺寸级」连通域候选，按 IoU 合并投票；
几何验证：尺寸≈2×小字格、墨量≈4 小字、粗笔画、落在注文格点上。
输出：work/lead/layout_ensemble_boxes.jsonl（page/boxes/evidence）
"""
import json, os, sys
import numpy as np, cv2, fitz
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def page_gray(vol, pno, dpi=150):
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
    pix = doc[pno - 1].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    g = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    doc.close()
    return g


def bin_otsu(g):
    bg = cv2.medianBlur(g, 41)
    flat = np.clip(g.astype(np.int16) - bg.astype(np.int16) + 200, 0, 255).astype(np.uint8)
    thr, _ = cv2.threshold(flat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return (flat < max(100, int(thr) - 5)).astype(np.uint8)


def bin_contrast(g):
    bg = cv2.medianBlur(g, 41)
    ratio = (bg.astype(np.float32) - g.astype(np.float32)) / np.maximum(bg, 1)
    return (ratio > 0.18).astype(np.uint8)


def bin_sauvola(g, w=25, k=0.22):
    g32 = g.astype(np.float32)
    m = cv2.boxFilter(g32, -1, (w, w))
    m2 = cv2.boxFilter(g32 * g32, -1, (w, w))
    s = np.sqrt(np.maximum(m2 - m * m, 0))
    T = m * (1 + k * (s / 128.0 - 1))
    return (g32 < T).astype(np.uint8)


def clean(ink, min_area=20):
    n0, l0, s0, _ = cv2.connectedComponentsWithStats(ink, 8)
    allow = (s0[:, cv2.CC_STAT_AREA] >= min_area); allow[0] = False
    return allow[l0].astype(np.uint8)


def mask_stats(ink):
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, 8)
    comps = []
    dt = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
    for i in range(1, n):
        x, y, w, h, a = st[i]
        comps.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h), "a": int(a)})
    return comps, dt


def candidates_from(ink, dt, h0, small_area):
    """单路候选：大字尺寸级连通域（含扁平横画合并）。"""
    comps, _ = mask_stats(ink)
    small = [c for c in comps if 0.8 * h0 <= c["h"] <= 1.45 * h0 and c["a"] < 3.2 * small_area]
    out = []
    # 大字组件：h >= 1.5*h0 或 (扁平且宽>=1.6*h0)
    for c in comps:
        if c["a"] < 0.6 * small_area:
            continue
        if c["h"] >= 1.5 * h0 or (c["h"] < 0.6 * c["w"] and c["w"] >= 1.5 * h0):
            out.append([c["x"], c["y"], c["x"] + c["w"], c["y"] + c["h"]])
    # 扁平横画合并
    out = merge_flat(out, h0)
    return out


def merge_flat(boxes, h0):
    merged = []
    used = [False] * len(boxes)
    order = sorted(range(len(boxes)), key=lambda i: -(boxes[i][2] - boxes[i][0]))
    for i in order:
        if used[i]:
            continue
        a = list(boxes[i])
        used[i] = True
        changed = True
        while changed:
            changed = False
            for j in order:
                if used[j]:
                    continue
                b = boxes[j]
                if not (a[3] - a[1] < 0.62 * (a[2] - a[0]) and b[3] - b[1] < 0.62 * (b[2] - b[0])):
                    continue
                ox = max(0, min(a[2], b[2]) - max(a[0], b[0]))
                if ox < 0.6 * min(a[2] - a[0], b[2] - b[0]):
                    continue
                gap = max(a[1], b[1]) - min(a[3], b[3])
                if gap <= 0.45 * h0:
                    a = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    used[j] = True; changed = True
        merged.append(a)
    return merged


def iou(a, b):
    x0 = max(a[0], b[0]); y0 = max(a[1], b[1]); x1 = min(a[2], b[2]); y1 = min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1]); ub = (b[2] - b[0]) * (b[3] - b[1])
    return inter / max(1, ua + ub - inter)


def detect(g):
    masks = {"otsu": clean(bin_otsu(g)), "contrast": clean(bin_contrast(g)), "sauvola": clean(bin_sauvola(g))}
    # 参考 h0/小字面积：用三路并集的稳定小字
    stats = {}
    for name, ink in masks.items():
        comps, dt = mask_stats(ink)
        small = [c for c in comps if 26 <= c["h"] <= 50 and 10 <= c["w"] <= 54 and 60 <= c["a"] <= 900]
        if len(small) < 100:
            stats[name] = None
            continue
        h0 = float(np.median([c["h"] for c in small]))
        sa = float(np.median([c["a"] for c in small]))
        stats[name] = (ink, dt, h0, sa)
    good = [v for v in stats.values() if v]
    if not good:
        return []
    h0 = float(np.median([v[2] for v in good]))
    sa = float(np.median([v[3] for v in good]))
    all_c = []
    for name, v in stats.items():
        if not v:
            continue
        ink, dt, h0m, sam = v
        for bb in candidates_from(ink, dt, h0m, sam):
            all_c.append({"box": [int(x) for x in bb], "method": name})
    # 按 IoU 聚类投票
    clusters = []
    for c in all_c:
        placed = False
        for cl in clusters:
            if iou(c["box"], cl["box"]) > 0.55:
                cl["votes"].add(c["method"])
                cl["n"] += 1
                placed = True
                break
        if not placed:
            clusters.append({"box": c["box"], "votes": {c["method"]}, "n": 1})
    # 几何验证
    ink_union = cv2.bitwise_or(cv2.bitwise_or(masks["otsu"], masks["contrast"]), masks["sauvola"])
    dt_union = cv2.distanceTransform(clean(ink_union, 20), cv2.DIST_L2, 3)
    out = []
    for cl in clusters:
        x0, y0, x1, y1 = cl["box"]
        w, h = x1 - x0, y1 - y0
        if not (1.25 * h0 <= max(w, h) <= 3.3 * h0):
            continue
        if min(w, h) < 0.45 * h0:
            continue
        sub = ink_union[y0:y1, x0:x1]
        a = int(sub.sum())
        if not (0.7 * sa <= a <= 8.5 * sa):
            continue
        dsub = dt_union[y0:y1, x0:x1]
        thick = int((dsub >= 3.5).sum())
        if thick < 0.01 * (w * h):
            continue
        out.append({"box": [x0, y0, x1, y1], "votes": sorted(cl["votes"]), "n_methods": len(cl["votes"]),
                    "ink": a, "thick": thick})
    return out, h0, sa


def detect_page(args):
    vol, pno = args
    try:
        g = page_gray(vol, pno)
        r = detect(g)
    except Exception as e:
        return {"page": f"{vol}_{pno:04d}", "boxes": [], "err": str(e)}
    if not r:
        return {"page": f"{vol}_{pno:04d}", "boxes": [], "meta": None}
    boxes, h0, sa = r
    return {"page": f"{vol}_{pno:04d}", "boxes": boxes,
            "h0": round(float(h0), 1), "small_area": round(float(sa), 1)}


def main():
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    jobs = []
    for vol, fn in sorted(mp.items()):
        doc = fitz.open(os.path.join(ROOT, "康熙字典", fn))
        n = doc.page_count; doc.close()
        for p in range(1, n + 1):
            jobs.append((vol, p))
    out = os.path.join(ROOT, "work/lead/layout_ensemble_boxes.jsonl")
    print("pages", len(jobs), flush=True)
    done = 0
    with ProcessPoolExecutor(max_workers=8) as ex, open(out, "w", encoding="utf-8") as fo:
        for res in ex.map(detect_page, jobs, chunksize=16):
            fo.write(json.dumps(res, ensure_ascii=False) + "\n")
            done += 1
            if done % 500 == 0:
                print("done", done, flush=True)
    print("finished", done, out, flush=True)


if __name__ == "__main__":
    main()
