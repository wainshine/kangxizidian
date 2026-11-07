#!/usr/bin/env python3
"""T1 · 切格器 v1

相对 T0 原型的三处改动（对应 docs/DECISIONS.md D9）：
1. 紧化改为中心分量法（只取与提议框中心 60% 区域重叠的连通域并集）——原型用
   膨胀并集回映，框平均松一半（IoU 0.507 的根因）；
2. NMS 去重（同一字形多次检出，金标制作时已暴露：增/乞/乁 各出现两个框）；
3. 硬判据过滤：墨团数=1（0.4×框高的子块数）、触边切割（框外 2px 环内墨迹占比）。

用法：t1_segment.py --mode orig|rect --pages 01_0006,01_0110,...
输出 work/t1/{mode}_boxes/{stem}.json
"""
import argparse, json, os
import numpy as np
import cv2

cv2.setNumThreads(1)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T00 = os.path.join(ROOT, "work", "t00")
T1 = os.path.join(ROOT, "work", "t1")


def page_ink(gray):
    ink = (gray <= 150).astype(np.uint8)
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 200))
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (200, 1))
    v = cv2.morphologyEx(ink, cv2.MORPH_OPEN, vk)
    h = cv2.morphologyEx(ink, cv2.MORPH_OPEN, hk)
    return cv2.subtract(cv2.subtract(ink, v), h)


def center_refine(ink, box):
    """中心分量紧化（t0_gold.refine 同款）：邻域内与中心 60% 区域重叠的连通域并集 bbox"""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    px, py = int(w * 0.2), int(h * 0.2)
    X0, Y0 = max(0, x0 - px), max(0, y0 - py)
    X1, Y1 = x1 + px, y1 + py
    sub = ink[Y0:Y1, X0:X1]
    n, lab, stats, _ = cv2.connectedComponentsWithStats(sub, connectivity=8)
    cx, cy = (x0 + x1) / 2 - X0, (y0 + y1) / 2 - Y0
    keep = np.zeros_like(sub, dtype=bool)
    for i in range(1, n):
        sx, sy, sw, sh, area = stats[i]
        if area < 30:
            continue
        # 中心 50% 区（60% 会把左邻字残片并进来，实测 dx -13~-19 系统左偏）
        ox = max(0, min(cx + w * 0.25, sx + sw) - max(cx - w * 0.25, sx))
        oy = max(0, min(cy + h * 0.25, sy + sh) - max(cy - h * 0.25, sy))
        if ox > 0 and oy > 0:
            keep |= (lab == i)
    ys, xs = np.where(keep)
    if len(xs) == 0:
        return None
    return [int(X0 + xs.min()), int(Y0 + ys.min()),
            int(X0 + xs.max()) + 1, int(Y0 + ys.max()) + 1]


def nms(boxes, thr=0.5):
    boxes = sorted(boxes, key=lambda b: -(b[2] - b[0]) * (b[3] - b[1]))
    keep = []
    for b in boxes:
        if all(iou(b, k) < thr for k in keep):
            keep.append(b)
    return keep


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua else 0.0


def hard_criteria(ink, box):
    """返回 (blobs_ok, edge_ok, info)。blobs：0.4×框高子块数必须=1；edge：框外 2px 环墨迹占比 <0.25"""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if w < 20 or h < 20:
        return False, False, {"reason": "tiny"}
    sub = ink[max(0, y0 - 4):y1 + 4, max(0, x0 - 4):x1 + 4]
    ox0, oy0 = max(0, x0 - 4), max(0, y0 - 4)
    inner = sub[y0 - oy0:y1 - oy0, x0 - ox0:x1 - ox0]
    kc = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    closed = cv2.morphologyEx(inner, cv2.MORPH_CLOSE, kc)
    n, _, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    big = sum(1 for i in range(1, n) if stats[i, 3] >= 0.4 * h and stats[i, 4] >= 60)
    blobs_ok = big == 1
    # 触边：框外 2px 环（环形区域）
    ring_mask = np.ones(sub.shape, dtype=bool)
    ring_mask[y0 - oy0:y1 - oy0, x0 - ox0:x1 - ox0] = False
    outer_ring = ring_mask & (sub > 0)
    perim = 2 * (w + h)
    edge_frac = outer_ring.sum() / max(1, perim * 2)
    edge_ok = edge_frac < 0.25
    return blobs_ok, edge_ok, {"blobs": int(big), "edge_frac": round(float(edge_frac), 3)}


def dense_enough(ink, box, min_frac=0.08):
    """邻域墨密度（T0 已验证：书眉字/孤立字周围空白，字头嵌在注文中间）"""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    s = max(w, h)
    Hh, Ww = ink.shape
    nx0, ny0 = max(0, x0 - s), max(0, y0 - s)
    nx1, ny1 = min(Ww, x1 + s), min(Hh, y1 + s)
    ring = np.ones((ny1 - ny0, nx1 - nx0), dtype=bool)
    ring[y0 - ny0:y1 - ny0, x0 - nx0:x1 - nx0] = False
    outside = ink[ny0:ny1, nx0:nx1][ring]
    return float((outside > 0).mean()) >= min_frac


def merge_splits(cands):
    """同列相邻候选合并：腐蚀把字形左右部件拆成两个 blob 时，各自紧化成半字。
    x 中心距 < 0.6×max(w) 且 y 重叠 ≥0.35×min(h) → 合并。"""
    changed = True
    while changed:
        changed = False
        out = []
        used = [False] * len(cands)
        for i, a in enumerate(cands):
            if used[i]:
                continue
            used[i] = True
            merged = list(a)
            ax = (a[0] + a[2]) / 2
            for j in range(i + 1, len(cands)):
                if used[j]:
                    continue
                b = cands[j]
                bx = (b[0] + b[2]) / 2
                if abs(ax - bx) > 0.6 * max(a[2] - a[0], b[2] - b[0]):
                    continue
                oy = min(a[3], b[3]) - max(a[1], b[1])
                if oy < 0.35 * min(a[3] - a[1], b[3] - b[1]):
                    continue
                ha, hb = a[3] - a[1], b[3] - b[1]
                if not (0.6 <= ha / hb <= 1.4):
                    continue  # 高度悬殊 = 字头+夹注，不许并
                cand = [min(merged[0], b[0]), min(merged[1], b[1]),
                        max(merged[2], b[2]), max(merged[3], b[3])]
                # 纵向过并防护：合并后高度不得超过较高者的 1.5 倍
                if cand[3] - cand[1] > 1.5 * max(ha, hb):
                    continue
                merged = cand
                used[j] = True
                changed = True
            out.append(merged)
        cands = out
    return cands


def segment_half(gray):
    """单版切格：提议（腐蚀/膨胀）→ 中心紧化 → 拆字合并 → NMS → 硬判据+密度过滤"""
    ink = page_ink(gray)
    cores = cv2.erode(ink, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    blobs = cv2.dilate(cores, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (18, 18)))
    nb, _, sb, _ = cv2.connectedComponentsWithStats(blobs, connectivity=8)
    Hh, Ww = ink.shape
    cands, dropped = [], []
    for i in range(1, nb):
        x, y, w, h, area = sb[i]
        if max(w, h) < 45 or w >= 12 * h or h >= 12 * w:
            continue
        r = center_refine(ink, (x, y, x + w, y + h))
        if r is None or max(r[2] - r[0], r[3] - r[1]) < 45:
            continue
        cands.append(r)
    cands = merge_splits(cands)
    cands = nms(cands)
    out, edge_flags = [], []
    for b in cands:
        x0, y0, x1, y1 = b
        if x0 < 8 or y0 < 8 or x1 > Ww - 8 or y1 > Hh - 8:
            dropped.append({"box": b, "why": "edge"})
            continue
        if not dense_enough(ink, b):
            dropped.append({"box": b, "why": "density"})
            continue
        blobs_ok, edge_ok, info = hard_criteria(ink, b)
        if not blobs_ok:
            # 墨团数>1 = 并格（一格两字），真失败，丢弃；=0 也异常，丢弃
            dropped.append({"box": b, "why": info})
            continue
        # 触边只标记不丢弃：密排页紧框天然贴墨，邻字归属由 T2 记账解决（D9 修正）
        out.append(b)
        edge_flags.append({"edge_flag": not edge_ok, **info})
    return out, dropped, edge_flags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["orig", "rect"], default="orig")
    ap.add_argument("--pages", default="01_0006,01_0110,13_0163,08_0020,01_0027,02_0155")
    args = ap.parse_args()
    os.makedirs(os.path.join(T1, f"{args.mode}_boxes"), exist_ok=True)
    for stem in args.pages.split(","):
        if args.mode == "orig":
            path = os.path.join(T00, "pages", stem + ".png")
            if not os.path.exists(path):
                print("missing", path); continue
            gray = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            halves = [("full", gray)]
        else:
            path = os.path.join(T00, "rect", f"{stem}_L.png")
            halves = []
            for side in "LR":
                p = os.path.join(T00, "rect", f"{stem}_{side}.png")
                if os.path.exists(p):
                    halves.append((side, cv2.imread(p, cv2.IMREAD_GRAYSCALE)))
        all_boxes, all_dropped, all_flags = [], [], []
        for side, g in halves:
            boxes, dropped, flags = segment_half(g)
            all_boxes += boxes
            all_dropped += dropped
            all_flags += flags
        json.dump({"mode": args.mode, "page": stem, "n": len(all_boxes),
                   "boxes": all_boxes, "dropped": all_dropped[:50],
                   "edge_flags": all_flags[:80],
                   "edge_violation_rate": round(sum(f["edge_flag"] for f in all_flags) / max(1, len(all_flags)), 3)},
                  open(os.path.join(T1, f"{args.mode}_boxes", stem + ".json"), "w"),
                  ensure_ascii=False, indent=1)
        print(stem, args.mode, "boxes:", len(all_boxes), "dropped:", len(all_dropped))


if __name__ == "__main__":
    main()
