#!/usr/bin/env python3
"""T0 · 版面参数实测（300 dpi 探针页）

量：版框位置、列数/列宽/列距、注文高度众数 h0、字头高度分布、每列字数、页边距。
所有阈值随 dpi 缩放（scale = dpi/150），不写死绝对像素。

输出 work/t00/probe_measure.json + 摘要打印
"""
import json, os, sys
import numpy as np
import cv2

cv2.setNumThreads(1)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T00 = os.path.join(ROOT, "work", "t00")

BIN_T = 150
HALF_BLANK_INK = 0.004


def page_ink(gray, scale):
    ink = (gray <= BIN_T).astype(np.uint8)
    L = int(200 * scale)
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, L))
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (L, 1))
    v = cv2.morphologyEx(ink, cv2.MORPH_OPEN, vk)
    h = cv2.morphologyEx(ink, cv2.MORPH_OPEN, hk)
    return cv2.subtract(cv2.subtract(ink, v), h)


def split_halves(ink, W):
    colsum = ink.sum(axis=0)
    best, run = None, None
    for x in range(int(W * 0.30), int(W * 0.70)):
        if colsum[x] == 0:
            run = run or x
        else:
            if run is not None:
                if best is None or x - run > best[1]:
                    best = (run, x - run)
                run = None
    if run is not None and (best is None or int(W * 0.7) - run > best[1]):
        best = (run, int(W * 0.7) - run)
    halves = [(0, best[0] if best else W // 2), ((best[0] + best[1]) if best else W // 2, W)]
    out = []
    for side, (x0, x1) in zip("LR", halves):
        blank = ink[:, x0:x1].mean() < HALF_BLANK_INK
        out.append((side, x0, x1, bool(blank)))
    return out


def columns_of(ink, x0, x1, scale):
    sub = ink[:, x0:x1]
    colsum = sub.sum(axis=0)
    on = colsum > max(30, int(0.02 * colsum.max()))
    cols, s = [], None
    for i, v_ in enumerate(on):
        if v_ and s is None:
            s = i
        elif not v_ and s is not None:
            if i - s >= 40 * scale:
                cols.append((s, i))
            s = None
    if s is not None:
        cols.append((s, len(on)))
    return cols, colsum


def measure(path):
    scale = 2.0 if "300" in os.path.basename(path) else 1.0
    gray = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    H, W = gray.shape
    ink = page_ink(gray, scale)
    res = {"file": os.path.basename(path), "W": W, "H": H, "dpi": 150 * scale, "halves": []}
    for side, x0, x1, blank in split_halves(ink, W):
        if blank:
            res["halves"].append({"side": side, "blank": True})
            continue
        sub = ink[:, x0:x1]
        # 版框：行投影的强带（>30% 宽）
        rowsum = sub.sum(axis=1)
        strong = np.where(rowsum > 0.30 * (x1 - x0))[0]
        strong = strong[(strong > 30 * scale) & (strong < H - 30 * scale)]
        fy0, fy1 = (int(strong.min()), int(strong.max())) if len(strong) else (None, None)
        # 列（在框内 y 范围）
        y0c = fy0 + 10 if fy0 else 0
        y1c = fy1 - 10 if fy1 else H
        band = sub[y0c:y1c, :]
        bsum = band.sum(axis=0)
        on = bsum > max(50, int(0.03 * bsum.max()))
        cols, s = [], None
        for i, v_ in enumerate(on):
            if v_ and s is None:
                s = i
            elif not v_ and s is not None:
                if i - s >= 30 * scale:
                    cols.append((s + x0, i + x0))
                s = None
        if s is not None:
            cols.append((s + x0, len(on) + x0))
        # 注文高度众数（raw blocks，全半页）
        n, _, stats, _ = cv2.connectedComponentsWithStats(sub, connectivity=8)
        hs = [int(stats[i, 3]) for i in range(1, n)
              if stats[i, 4] >= 30 and min(stats[i, 2], stats[i, 3]) >= 10 * scale
              and stats[i, 3] <= 70 * scale]
        h0 = None
        if len(hs) >= 20:
            bins = np.bincount([(h_ - 15) // 4 for h_ in hs], minlength=15)
            h0 = 15 + int(np.argmax(bins)) * 4 + 2
        res["halves"].append({
            "side": side, "x0": x0, "x1": x1, "frame_y": [fy0, fy1],
            "n_cols": len(cols),
            "col_widths_px": [c[1] - c[0] for c in cols],
            "col_pitch_px": [cols[i + 1][0] - cols[i][0] for i in range(len(cols) - 1)],
            "h0_px": h0 * scale if h0 else None,   # 归一到 150dpi 口径
        })
    return res


def main():
    pages = [p for p in sys.argv[1:]] or [
        os.path.join(T00, "probe300_01_0006.png"),
        os.path.join(T00, "probe300_01_0110.png"),
        os.path.join(T00, "probe300_13_0163.png"),
    ]
    out = [measure(p) for p in pages]
    json.dump(out, open(os.path.join(T00, "probe_measure.json"), "w"),
              ensure_ascii=False, indent=1)
    for r in out:
        print(r["file"], f"{r['dpi']:.0f}dpi")
        for h in r["halves"]:
            if h.get("blank"):
                print(f"  {h['side']}: blank")
                continue
            cw = h["col_widths_px"]
            cp = h["col_pitch_px"]
            print(f"  {h['side']}: frame_y={h['frame_y']} cols={h['n_cols']} "
                  f"col_w={np.median(cw) if cw else 0:.0f}±{np.std(cw) if cw else 0:.0f} "
                  f"pitch={np.median(cp) if cp else 0:.0f} h0(150dpi)={h['h0_px']}")


if __name__ == "__main__":
    main()
