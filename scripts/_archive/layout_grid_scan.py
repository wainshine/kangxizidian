#!/usr/bin/env python3
"""版面格点法大字检测（投影定格距 + 格内笔画厚度判别）。

核心（按业主提示）：注文小字构成规则格点阵；大字覆盖 2×2 格，单格笔画厚度约为小字 2 倍
（DT max 判别），总面积 ≈ 4 小字格。
步骤：
  1) 150dpi 渲染，背景相减二值（kernel 21 > 笔画厚），去斑；
  2) 全局 DT（一次），小字组件估计字高 h0；
  3) 行/列投影自相关 → 行距/列距 (py/px) 与相位；
  4) 每格取 ink 面积与 maxDT（积分图加速）；thick 格 = maxDT>=4.0 且面积>=0.2×小字面积；
  5) 2×2 全 thick 窗口 → 大字；框 = 窗口内 ink bbox（不越窗 → 无注文/边角料）；
  6) 输出 JSONL：page/half/box/ink/meanDT/cells。
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


def _boxsum(ii, y0, y1, x0, x1):
    return int(ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0])


def detect(gray):
    bg = cv2.medianBlur(gray, 21)
    diff = bg.astype(np.int16) - gray.astype(np.int16)
    ink = (diff > 42).astype(np.uint8)
    n0, l0, s0, _ = cv2.connectedComponentsWithStats(ink, 8)
    allow = (s0[:, cv2.CC_STAT_AREA] >= 12); allow[0] = False
    ink = allow[l0].astype(np.uint8)
    dt = cv2.distanceTransform(ink, cv2.DIST_L2, 5)
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, 8)
    small = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if 26 <= h <= 50 and 10 <= w <= 54 and 60 <= a <= 900:
            small.append((x, y, w, h, a))
    if len(small) < 120:
        return None
    h0 = float(np.median([s[3] for s in small]))
    small_area = float(np.median([s[4] for s in small]))
    # 投影：只看文本块（小字外接框内）
    xs = [s[0] for s in small]; xe = [s[0] + s[2] for s in small]
    ys = [s[1] for s in small]; ye = [s[1] + s[3] for s in small]
    X0, X1 = int(np.percentile(xs, 1)), int(np.percentile(xe, 99))
    Y0, Y1 = int(np.percentile(ys, 1)), int(np.percentile(ye, 99))
    sub = ink[Y0:Y1 + 1, X0:X1 + 1]
    colproj = sub.sum(axis=0).astype(np.float32)
    rowproj = sub.sum(axis=1).astype(np.float32)

    def autocorr_pitch(proj, lo, hi):
        x = proj - proj.mean()
        ac = np.correlate(x, x, "full")[len(x) - 1:]
        ac = ac / (ac[0] + 1e-6)
        best, bestv = None, -1
        for lag in range(lo, min(hi, len(ac) - 1)):
            if ac[lag] > bestv:
                bestv, best = ac[lag], lag
        return best, bestv

    px, pxc = autocorr_pitch(colproj, 34, 64)   # 列距（150dpi）
    py, pyc = autocorr_pitch(rowproj, 28, 44)   # 行距 ≈ 字高+缝
    if not px or not py:
        return None

    def phase(proj, pitch):
        best, bestv = 0, -1.0
        for off in range(int(pitch)):
            v = proj[off::int(pitch)].mean() if off < len(proj) else 0
            if v > bestv:
                bestv, best = v, off
        return best

    phx = phase(colproj, px) + X0
    phy = phase(rowproj, py) + Y0
    # 积分图：ink 面积、thick 像素数（DT>=4.0）
    ii = cv2.integral(ink)
    thick = (dt >= 4.0).astype(np.uint8)
    it = cv2.integral(thick)
    H, W = ink.shape
    cells_x = int((W - phx) // px) + 1
    cells_y = int((H - phy) // py) + 1
    thick_cells = set()
    for r in range(cells_y):
        y0 = int(phy + r * py); y1 = int(min(H, y0 + py))
        if y1 - y0 < 20:
            continue
        for c in range(cells_x):
            x0 = int(phx + c * px); x1 = int(min(W, x0 + px))
            if x1 - x0 < 20:
                continue
            a = _boxsum(ii, y0, y1, x0, x1)
            if a < max(40, 0.15 * small_area):
                continue
            tk = _boxsum(it, y0, y1, x0, x1)
            if tk >= 0.05 * (x1 - x0) * (y1 - y0):   # 有粗笔画（DT>=4）
                thick_cells.add((r, c))
    # 2×2 窗口
    out = []
    seen = set()
    for (r, c) in sorted(thick_cells):
        if all((r + dr, c + dc) in thick_cells for dr in (0, 1) for dc in (0, 1)):
            if (r, c) in seen:
                continue
            y0 = int(phy + r * py); y1 = int(min(H, phy + (r + 2) * py))
            x0 = int(phx + c * px); x1 = int(min(W, phx + (c + 2) * px))
            sub2 = ink[y0:y1, x0:x1]
            a = int(sub2.sum())
            if not (1.0 * small_area <= a <= 8 * small_area):
                continue
            ys2, xs2 = np.where(sub2 > 0)
            if len(xs2) < 40:
                continue
            out.append({"box": [int(x0 + xs2.min()), int(y0 + ys2.min()),
                                int(x0 + xs2.max() + 1), int(y0 + ys2.max() + 1)],
                        "ink": a, "cells": [r, c]})
            for dr in (0, 1):
                for dc in (0, 1):
                    seen.add((r + dr, c + dc))
    return {"boxes": out, "h0": round(h0, 1), "px": int(px), "py": int(py),
            "n_small": len(small), "small_area": round(small_area, 1)}


def detect_page(args):
    vol, pno, dpi = args
    try:
        g = page_gray(vol, pno, dpi)
        res = detect(g)
    except Exception as e:
        return {"page": f"{vol}_{pno:04d}", "boxes": [], "err": str(e)}
    if res is None:
        return {"page": f"{vol}_{pno:04d}", "boxes": [], "meta": None}
    res["page"] = f"{vol}_{pno:04d}"
    return res


def main():
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    jobs = []
    for vol, fn in sorted(mp.items()):
        doc = fitz.open(os.path.join(ROOT, "康熙字典", fn))
        n = doc.page_count; doc.close()
        for p in range(1, n + 1):
            jobs.append((vol, p, 150))
    out_path = os.path.join(ROOT, "work/lead/layout_grid_boxes.jsonl")
    print("pages", len(jobs), flush=True)
    done = 0
    with ProcessPoolExecutor(max_workers=8) as ex, open(out_path, "w", encoding="utf-8") as fo:
        for res in ex.map(detect_page, jobs, chunksize=16):
            fo.write(json.dumps(res, ensure_ascii=False) + "\n")
            done += 1
            if done % 500 == 0:
                print("done", done, flush=True)
    print("finished", done, out_path, flush=True)


if __name__ == "__main__":
    main()
