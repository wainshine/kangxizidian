#!/usr/bin/env python3
"""按「列距/行距严格格点」切字（源头修复 v2）。

康熙字典版式：注文小字 1 格；字头大字 = 2×2 格（面积≈4 小字）。
本脚本：
 1) 每半版拟合列距 px、行距 py、相位（小字中心，稳健拟合）；
 2) 每格计算墨量 + 笔画半宽(distanceTransform)：区分「小字格 / 字格（大字）/ 空白格」；
 3) 以 2×2 窗口聚合「字格」，块内墨量 ≈ 2.5~8× 小字墨量 → 字头候选；
 4) 字头框 = 2×2 格块边界（严格按格点，不做逐字 trim）。
输出 work/lead/grid_v2_boxes.jsonl
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


def binarize(g):
    bg = cv2.medianBlur(g, 21)
    diff = bg.astype(np.int16) - g.astype(np.int16)
    ink = (diff > 40).astype(np.uint8)
    n0, l0, s0, _ = cv2.connectedComponentsWithStats(ink, 8)
    allow = (s0[:, cv2.CC_STAT_AREA] >= 15); allow[0] = False
    return allow[l0].astype(np.uint8)


def fit_axis(vals, lo, hi, tol=0.18):
    best = (0, 42.0, 0.0)
    for pitch in np.arange(lo, hi + 0.001, 0.5):
        ang = np.mod(vals, pitch) / pitch * 2 * np.pi
        ph = (np.angle(np.mean(np.exp(1j * ang))) / (2 * np.pi)) % 1.0 * pitch
        d = np.abs(np.mod(vals - ph + pitch / 2, pitch) - pitch / 2)
        score = int((d < tol * pitch).sum())
        if score > best[0]:
            best = (score, pitch, ph)
    return best


def detect_half(gray, ink, mask, dt):
    h, w = gray.shape
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, 8)
    small = []
    for i in range(1, n):
        x, y, ww, hh, a = [int(v) for v in st[i]]
        if not mask(x + ww / 2, y + hh / 2):
            continue
        if 24 <= hh <= 54 and 9 <= ww <= 60 and 40 <= a <= 1200:
            small.append({"cx": x + ww / 2, "cy": y + hh / 2, "h": hh, "a": a,
                          "dt": float(dt[y:y + hh, x:x + ww].max())})
    if len(small) < 120:
        return None
    h0 = float(np.median([s["h"] for s in small]))
    small_ink = float(np.median([s["a"] for s in small]))
    small_dt = float(np.median([s["dt"] for s in small]))
    xs = np.array([s["cx"] for s in small]); ys = np.array([s["cy"] for s in small])
    sx, px, phx = fit_axis(xs, 0.9 * h0, 1.9 * h0)
    sy, py, phy = fit_axis(ys, 0.85 * h0, 1.6 * h0)
    def refine(vals, pitch, phase):
        lag = np.mod(vals - phase + pitch / 2, pitch) - pitch / 2
        return phase + float(np.median(lag))
    phx = refine(xs, px, phx); phy = refine(ys, py, phy)
    # 文本块范围（小字分布）
    tx0 = float(np.percentile(xs, 1)) - px; tx1 = float(np.percentile(xs, 99)) + px
    ty0 = float(np.percentile(ys, 1)) - py; ty1 = float(np.percentile(ys, 99)) + py
    # 网格
    c0 = int(np.floor((min(tx0, mask(0, 0) and 0 or 0) - phx) / px)) if False else int(np.floor((tx0 - phx) / px))
    # 对每半版扫一遍格
    cell = {}
    r_lo = int(np.floor((ty0 - phy) / py)); r_hi = int(np.ceil((ty1 - phy) / py))
    c_lo = int(np.floor((tx0 - phx) / px)); c_hi = int(np.ceil((tx1 - phx) / px))
    def cell_rect(r, c):
        x0 = int(round(phx + c * px)); y0 = int(round(phy + r * py))
        return (x0, y0, int(round(x0 + px)), int(round(y0 + py)))
    for r in range(r_lo, r_hi + 1):
        for c in range(c_lo, c_hi + 1):
            x0, y0, x1, y1 = cell_rect(r, c)
            if x0 < 0 or y0 < 0 or x1 >= w or y1 >= h:
                continue
            sub = ink[y0:y1, x0:x1]
            a = int(sub.sum())
            dmax = float(dt[y0:y1, x0:x1].max())
            cell[(r, c)] = {"ink": a, "dt": dmax}
    # 分类：字格（大字笔画粗） / 小字格 / 空白
    def is_big(cl):
        return cl["dt"] >= max(small_dt * 1.5, small_dt + 1.2) and cl["ink"] >= 0.35 * small_ink
    big = {k for k, v in cell.items() if is_big(v)}
    blocks = []
    seen = set()
    for (r, c) in sorted(big):
        if (r, c) in seen:
            continue
        # 尝试以 (r,c) 为左上 / 或作为块内某格，搜索 2x2 块
        best = None
        for dr in (-1, 0):
            for dc in (-1, 0):
                r0, c0 = r + dr, c + dc
                cells = [(r0 + i, c0 + j) for i in (0, 1) for j in (0, 1)]
                if any(cc not in cell for cc in cells):
                    continue
                nb = sum(1 for cc in cells if cc in big)
                a = sum(cell[cc]["ink"] for cc in cells)
                if nb >= 3 and 1.5 * small_ink <= a <= 9 * small_ink:
                    if best is None or a > best[0]:
                        best = (a, r0, c0, cells)
        if best is None:
            continue
        a, r0, c0, cells = best
        if any(cc in seen for cc in cells):
            continue
        x0, y0, _, _ = cell_rect(r0, c0)
        x1 = int(round(x0 + 2 * px)); y1 = int(round(y0 + 2 * py))
        blocks.append({"box": [x0, y0, x1, y1], "ink": int(a), "cell": [r0, c0]})
        seen.update(cells)
    return {"blocks": blocks, "h0": round(h0, 1), "px": round(float(px), 2),
            "py": round(float(py), 2), "phx": round(float(phx), 1), "phy": round(float(phy), 1),
            "small_ink": round(small_ink, 1), "small_dt": round(small_dt, 2),
            "resid_x": round(float(np.median(np.abs(np.mod(xs - phx + px / 2, px) - px / 2)) / px), 3),
            "resid_y": round(float(np.median(np.abs(np.mod(ys - phy + py / 2, py) - py / 2)) / py), 3)}


def detect_page(args):
    vol, pno = args
    try:
        g = page_gray(vol, pno)
    except Exception as e:
        return {"page": f"{vol}_{pno:04d}", "halves": {}, "err": str(e)[:80]}
    h, w = g.shape
    ink = binarize(g)
    dt = cv2.distanceTransform(ink, cv2.DIST_L2, 5)
    col = ink.sum(axis=0).astype(np.float32)
    lo, hi = int(w * 0.42), int(w * 0.58)
    gx = int(lo + np.argmin(col[lo:hi]))
    out = {"page": f"{vol}_{pno:04d}", "gutter": gx, "halves": {}}
    for name, m in (("L", lambda x, y: x < gx), ("R", lambda x, y: x >= gx)):
        r = detect_half(g, ink, m, dt)
        if r:
            out["halves"][name] = r
    return out


def main():
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    jobs = []
    for vol, fn in sorted(mp.items()):
        doc = fitz.open(os.path.join(ROOT, "康熙字典", fn)); n = doc.page_count; doc.close()
        for p in range(1, n + 1):
            jobs.append((vol, p))
    out = os.path.join(ROOT, "work/lead/grid_v2_boxes.jsonl")
    print("pages", len(jobs), flush=True)
    done = 0
    with ProcessPoolExecutor(max_workers=8) as ex, open(out, "w", encoding="utf-8") as fo:
        for res in ex.map(detect_page, jobs, chunksize=8):
            fo.write(json.dumps(res, ensure_ascii=False) + "\n")
            done += 1
            if done % 1000 == 0:
                print("done", done, flush=True)
    print("finished", done, out, flush=True)


if __name__ == "__main__":
    main()
