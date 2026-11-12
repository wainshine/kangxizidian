#!/usr/bin/env python3
"""从头重建（v2.4.21）：从扫描页独立检测字头块（不依赖历史 mapping）。

版式模型（已由 39 条锚点验证）：
  小字中心 = 格点节点 (phx + c*px, phy + r*py)
  字头大字 = 2×2 格块 = [phx+(c-1/2)px, phy+(r-1/2)py, +2px, +2py]
检测流程（每页/半版）：
  1) 小字组件（高≈h0）→ 拟合 px/py/相位；
  2) 建格点占用：格内有小字中心 → 注文格；
  3) 对每个「非注文格」的 2×2 窗口：块内墨量 ∈ [1.2, 8]×小字墨量，且块内墨 bbox 四周留边 ≥4%；
  4) 去重（按块得分保留最佳）。
输出 work/lead/blocks_from_scratch.jsonl
"""

# --- 并发守卫（AGENTS.md：≤10 workers / CPU≤2000%；先限线程再导入重库）---
import os as _os
for _k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ.setdefault(_k, "1")
try:
    import cv2 as _cv2
    _cv2.setNumThreads(1)
except Exception:
    pass



import json, os, sys
import numpy as np, cv2, fitz
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MP = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))


def page_gray(vol, pno, dpi=150):
    doc = fitz.open(os.path.join(ROOT, "康熙字典", MP[vol]))
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


def detect_half(gray, ink, mask):
    h, w = gray.shape
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, 8)
    small = []
    for i in range(1, n):
        x, y, ww, hh, a = [int(v) for v in st[i]]
        if not mask(x + ww / 2, y + hh / 2):
            continue
        if 24 <= hh <= 54 and 9 <= ww <= 60 and 40 <= a <= 1200:
            small.append((x + ww / 2, y + hh / 2, hh, a))
    if len(small) < 120:
        return None
    h0 = float(np.median([s[2] for s in small]))
    s_ink = float(np.median([s[3] for s in small]))
    xs = np.array([s[0] for s in small]); ys = np.array([s[1] for s in small])
    syn, px, phx = fit_axis(xs, 0.9 * h0, 1.9 * h0)
    syy, py, phy = fit_axis(ys, 0.85 * h0, 1.6 * h0)
    def refine(vals, pitch, phase):
        lag = np.mod(vals - phase + pitch / 2, pitch) - pitch / 2
        return phase + float(np.median(lag))
    phx = refine(xs, px, phx); phy = refine(ys, py, phy)
    # 格点占用（小字中心）
    occ = set()
    for (cx, cy, hh, a) in small:
        c = int(round((cx - phx) / px)); r = int(round((cy - phy) / py))
        occ.add((r, c))
    # 文本范围
    tx0 = float(np.percentile(xs, 1)); tx1 = float(np.percentile(xs, 99))
    ty0 = float(np.percentile(ys, 1)); ty1 = float(np.percentile(ys, 99))
    c_lo = int(np.floor((tx0 - 2 * px - phx) / px)); c_hi = int(np.ceil((tx1 + 2 * px - phx) / px))
    r_lo = int(np.floor((ty0 - 2 * py - phy) / py)); r_hi = int(np.ceil((ty1 + 2 * py - phy) / py))
    cands = []
    for r in range(r_lo, r_hi):
        for c in range(c_lo, c_hi):
            if any((r + dr, c + dc) in occ for dr in (0, 1) for dc in (0, 1)):
                continue
            x0 = int(round(phx + (c - 0.5) * px)); y0 = int(round(phy + (r - 0.5) * py))
            x1 = int(round(x0 + 2 * px)); y1 = int(round(y0 + 2 * py))
            if x0 < 0 or y0 < 0 or x1 >= w or y1 >= h:
                continue
            sub = ink[y0:y1, x0:x1]
            a = int(sub.sum())
            if not (1.2 * s_ink <= a <= 8.0 * s_ink):
                continue
            ys_, xs_ = np.nonzero(sub)
            if len(xs_) == 0:
                continue
            bw, bh = x1 - x0, y1 - y0
            m = [xs_.min() / bw, ys_.min() / bh, (bw - xs_.max()) / bw, (bh - ys_.max()) / bh]
            notes = {"margins": m}
            # 字头墨迹通常填满 2×2 块（墨会touch块边），因此不设留边阈值；
            # 但要求墨迹「跨过」块中心区域，且块边不超出文本范围
            cxr = (xs_.min() + xs_.max()) / 2.0 / bw - 0.5
            cyr = (ys_.min() + ys_.max()) / 2.0 / bh - 0.5
            if abs(cxr) > 0.22 or abs(cyr) > 0.22:
                continue
            # 块整体应落在文本范围内（含半格容差）
            if x0 < tx0 - 1.0 * px or y0 < ty0 - 1.0 * py or x1 > tx1 + 1.0 * px or y1 > ty1 + 1.0 * py:
                continue
            # 块内不应含「小字中心」
            n_small_inside = 0
            for (cx, cy, hh, aa) in small:
                if x0 <= cx < x1 and y0 <= cy < y1:
                    n_small_inside += 1
            if n_small_inside:
                continue
            score = a / s_ink - 20 * (abs(cxr) + abs(cyr))
            cands.append({"box": [x0, y0, x1, y1], "ink": a, "cell": [r, c], "score": round(score, 3)})
    # 去重：按 score 降序，重叠>30% 的保留高者
    cands.sort(key=lambda x: -x["score"])
    kept = []
    def iou(a, b):
        x0, y0 = max(a[0], b[0]), max(a[1], b[1]); x1, y1 = min(a[2], b[2]), min(a[3], b[3])
        inter = max(0, x1 - x0) * max(0, y1 - y0)
        ua = (a[2]-a[0])*(a[3]-a[1]); ub = (b[2]-b[0])*(b[3]-b[1])
        return inter / max(1, ua + ub - inter)
    for c in cands:
        if any(iou(c["box"], k["box"]) > 0.3 for k in kept):
            continue
        kept.append(c)
    return {"blocks": kept, "h0": round(h0, 1), "s_ink": round(s_ink, 1),
            "px": round(float(px), 2), "py": round(float(py), 2),
            "n_small": len(small)}


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
    for name, m in (("L", lambda x, y: x < gx), ("R", lambda x, y: x >= gx)):
        r = detect_half(g, ink, m)
        if r:
            out["halves"][name] = r
    return out


def main():
    jobs = []
    for vol, fn in sorted(MP.items()):
        doc = fitz.open(os.path.join(ROOT, "康熙字典", fn)); n = doc.page_count; doc.close()
        for p in range(1, n + 1):
            jobs.append((vol, p))
    out = os.path.join(ROOT, "work/lead/blocks_from_scratch.jsonl")
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
