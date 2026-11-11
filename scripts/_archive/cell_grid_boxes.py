#!/usr/bin/env python3
"""源头修复（类级）：按康熙字典版式「字格」推导字头框。

版式事实：注文小字占 1 格；字头大字占 2×2 格（面积≈4 个小字）。
步骤（每页/每半版）：
  1) 背景相减二值；找小字组件（高≈h0）→ 拟合 x/y 格距与相位（最小残差）；
  2) 建字格占用网格：格内出现小字中心 = 占用；
  3) 2×2 连续空格 = 字头候选；校验：块内墨量≈2~8 倍小字墨量、四象限有墨；
  4) 字头框 = 2×2 格块边界（源头即正确，不 trim、不缩放）。
输出 work/lead/cell_grid_boxes.jsonl
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
    """1D 格点拟合：返回 (pitch, phase, score)。"""
    best = (0, 42.0, 0.0)
    for pitch in np.arange(lo, hi + 0.001, 0.5):
        ang = np.mod(vals, pitch) / pitch * 2 * np.pi
        ph = (np.angle(np.mean(np.exp(1j * ang))) / (2 * np.pi)) % 1.0 * pitch
        d = np.abs(np.mod(vals - ph + pitch / 2, pitch) - pitch / 2)
        score = int((d < tol * pitch).sum())
        if score > best[0]:
            best = (score, pitch, ph)
    return best


def detect_half(gray, mask):
    h, w = gray.shape
    ink = binarize(gray)
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, 8)
    small = []
    for i in range(1, n):
        x, y, ww, hh, a = [int(v) for v in st[i]]
        if not mask(x + ww / 2, y + hh / 2):
            continue
        if 24 <= hh <= 54 and 9 <= ww <= 60 and 40 <= a <= 1200:
            small.append({"cx": x + ww / 2, "cy": y + hh / 2, "h": hh, "w": ww, "a": a})
    if len(small) < 150:
        return None
    h0 = float(np.median([s["h"] for s in small]))
    w0 = float(np.median([s["w"] for s in small]))
    xs = np.array([s["cx"] for s in small]); ys = np.array([s["cy"] for s in small])
    sx, px, phx = fit_axis(xs, 0.9 * h0, 1.9 * h0)
    sy, py, phy = fit_axis(ys, 0.85 * h0, 1.6 * h0)
    if sx < 0.55 * len(small) or sy < 0.55 * len(small):
        return None
    # 相位精修：把落点残差用线性回归压到 0
    def refine(vals, pitch, phase):
        lag = np.mod(vals - phase + pitch / 2, pitch) - pitch / 2
        return phase + float(np.median(lag))
    phx = refine(xs, px, phx); phy = refine(ys, py, phy)
    # 文本块范围
    tx0 = float(np.percentile(xs, 1)) - px; tx1 = float(np.percentile(xs, 99)) + px
    ty0 = float(np.percentile(ys, 1)) - py; ty1 = float(np.percentile(ys, 99)) + py
    # 占用网格
    def cell_idx(v, pitch, phase):
        return np.round((v - phase) / pitch).astype(int)
    cxs = cell_idx(xs, px, phx); cys = cell_idx(ys, py, phy)
    rmin, rmax = int(cys.min()) - 2, int(cys.max()) + 2
    cmin, cmax = int(cxs.min()) - 2, int(cxs.max()) + 2
    nr, nc = rmax - rmin + 1, cmax - cmin + 1
    occ = np.zeros((nr, nc), np.uint8)
    for c, r in zip(cxs, cys):
        rr, cc = int(r) - rmin, int(c) - cmin
        if 0 <= rr < nr and 0 <= cc < nc:
            occ[rr, cc] = 1
    small_ink = float(np.median([s["a"] for s in small]))
    boxes = []
    seen = set()
    for r in range(nr - 1):
        for c in range(nc - 1):
            if occ[r:r + 2, c:c + 2].any():
                continue
            if any((r + dr, c + dc) in seen for dr in (0, 1) for dc in (0, 1)):
                continue
            x0 = int(round(phx + (c + cmin) * px)); y0 = int(round(phy + (r + rmin) * py))
            x1 = int(round(x0 + 2 * px)); y1 = int(round(y0 + 2 * py))
            if x0 < tx0 - px or y0 < ty0 - py or x1 > tx1 + px or y1 > ty1 + py:
                continue
            if x0 < 0 or y0 < 0 or x1 >= w or y1 >= h:
                continue
            sub = ink[y0:y1, x0:x1]
            a = int(sub.sum())
            if not (1.0 * small_ink <= a <= 9 * small_ink):
                continue
            H, W = sub.shape
            quads = [sub[:H // 2, :W // 2].sum(), sub[:H // 2, W // 2:].sum(),
                     sub[H // 2:, :W // 2].sum(), sub[H // 2:, W // 2:].sum()]
            if min(quads) < 0.03 * a:
                continue
            for dr in (0, 1):
                for dc in (0, 1):
                    seen.add((r + dr, c + dc))
            boxes.append({"box": [x0, y0, x1, y1], "ink": a, "cell": [r + rmin, c + cmin]})
    return {"boxes": boxes, "h0": round(h0, 1), "px": round(float(px), 2),
            "py": round(float(py), 2), "n_small": len(small),
            "resid_x": round(float(np.median(np.abs(np.mod(xs - phx + px/2, px) - px/2)) / px), 3),
            "resid_y": round(float(np.median(np.abs(np.mod(ys - phy + py/2, py) - py/2)) / py), 3)}


def detect_page(args):
    vol, pno = args
    try:
        g = page_gray(vol, pno)
    except Exception as e:
        return {"page": f"{vol}_{pno:04d}", "halves": {}, "err": str(e)[:80]}
    h, w = g.shape
    ink = binarize(g)
    col = ink.sum(axis=0).astype(np.float32)
    lo, hi = int(w * 0.42), int(w * 0.58)
    gx = int(lo + np.argmin(col[lo:hi]))
    out = {"page": f"{vol}_{pno:04d}", "gutter": gx, "halves": {}}
    for name, mask in (("L", lambda x, y: x < gx), ("R", lambda x, y: x >= gx)):
        r = detect_half(g, mask)
        if r:
            out["halves"][name] = r
    return out


def main():
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    jobs = []
    for vol, fn in sorted(mp.items()):
        doc = fitz.open(os.path.join(ROOT, "康熙字典", fn))
        n = doc.page_count; doc.close()
        for p in range(1, n + 1):
            jobs.append((vol, p))
    out = os.path.join(ROOT, "work/lead/cell_grid_boxes.jsonl")
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
