#!/usr/bin/env python3
"""试验：边角料（邻字/栏线残片）清除 —— 对比旧 clean_ink 与新规则。"""
import json, os, sys
import numpy as np
import cv2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from font_norm import binarize, clean_ink, render_pdf_crop, trace  # noqa


def clean_ink_v2(ink, box, thin_thr=14, min_area=40):
    """box=crop 内字身框像素坐标 (x0,y0,x1,y1)。规则：
    1) 主成分保留；
    2) 成分中心在 box 内 -> 保留；
    3) 中心在 box 外：仅当「厚」（min(w,h)>thin_thr）且 bbox 与 box 交叠 >=50% -> 保留（被框切到的真笔画）；
    4) 其余 -> 丢弃（邻字/栏线/注文残片）。
    """
    n, lab, stats, cent = cv2.connectedComponentsWithStats(ink.astype(np.uint8), 8)
    if n <= 1:
        return ink
    X, Y, W, H, A = 0, 1, 2, 3, 4
    bx0, by0, bx1, by1 = box
    main = 1 + int(np.argmax(stats[1:, A]))
    keep = np.zeros(n, bool)
    for i in range(1, n):
        if i == main:
            keep[i] = True
            continue
        x, y, w, h, a = (stats[i, X], stats[i, Y], stats[i, W], stats[i, H], stats[i, A])
        cx, cy = cent[i]
        if bx0 <= cx <= bx1 and by0 <= cy <= by1:
            keep[i] = True
            continue
        if min(w, h) > thin_thr:
            ix0, iy0 = max(x, bx0), max(y, by0)
            ix1, iy1 = min(x + w, bx1), min(y + h, by1)
            inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
            if inter >= 0.5 * w * h:
                keep[i] = True
    if not keep.any():
        keep[main] = True
    return keep[lab]


def main():
    union = json.load(open(os.path.join(ROOT, "work/lead/confirmed_union9.json")))
    items = list(union.items())
    # 采样并对比组件差异
    import random
    random.seed(7)
    picked = random.sample(items, 400)
    diffs = []
    for ch, rec in picked:
        page, box = rec["page"], rec["box"]
        gray = render_pdf_crop(page, box)
        pad = 6 * 2  # render_pdf_crop pad150=6 -> 300dpi 12px
        b = [pad, pad, pad + (box[2] - box[0]) * 2, pad + (box[3] - box[1]) * 2]
        ink = binarize(gray)
        old = clean_ink(ink, center=b, border_margin=1)
        new = clean_ink_v2(ink, b)
        d_old = int(old.sum()); d_new = int(new.sum())
        if d_new < d_old * 0.995:
            diffs.append((ch, page, box, int(ink.sum()), d_old, d_new))
    print("differ", len(diffs), "/", len(picked))
    for d in diffs[:20]:
        print(d)
    json.dump(diffs, open(os.path.join(ROOT, "work/lead/edge_clean_diff.json"), "w"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
