#!/usr/bin/env python3
"""参考结构闸（语义锚）：把每个成品字形与参考字体同字做组件级对比，
找出「在参考结构里找不到对应墨迹」的悬浮小组件（框线/邻字碎片）。

原理：标签（字）是语义锚。一个孤立小钩/小逗点若是部件，参考字体同字对应位置必有墨；
若参考里没有 → 属于污染碎片。风格差异用「参考墨迹膨胀 4-6px」容忍。
"""
import json, os, sys
import numpy as np, cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SONGTI = "/System/Library/Fonts/Supplemental/Songti.ttc"
SIZE = 256
DILATE = 5


def raster(font_path, ch, size=SIZE, index=None):
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype(font_path, size) if index is None else ImageFont.truetype(font_path, size, index=index)
    im = Image.new("L", (size, size), 0)
    ImageDraw.Draw(im).text((size // 2, int(0.88 * size)), ch, fill=255, font=f, anchor="ms")
    return np.array(im) > 127


def analyze(our_mask, ref_mask, dilate=DILATE, min_area=12):
    """返回可疑组件列表（像素 bbox / 面积 / 参考覆盖率）。"""
    n, lab, st, _ = cv2.connectedComponentsWithStats(our_mask.astype(np.uint8), 8)
    if n <= 1:
        return []
    ref_d = cv2.dilate(ref_mask.astype(np.uint8), np.ones((2 * dilate + 1, 2 * dilate + 1), np.uint8)) > 0
    out = []
    total = int(our_mask.sum())
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a < min_area:
            continue
        comp = (lab == i)
        cov = float((comp & ref_d).sum()) / max(1, a)
        if cov < 0.15 and a < 0.006 * total:
            out.append({"bbox": [int(x), int(y), int(x + w), int(y + h)], "area": int(a),
                        "cov": round(cov, 3)})
    return out


def glyph_masks(our_font, ch, size=SIZE):
    ours = raster(our_font, ch, size)
    ref = raster(SONGTI, ch, size, index=7)
    return ours, ref


if __name__ == "__main__":
    font = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "release/KangXiKai-v2.4.12/KangXiKai-Regular-v2.4.12.ttf")
    for ch in (sys.argv[2] if len(sys.argv) > 2 else "路佇耄嗃永和國一十"):
        ours, ref = glyph_masks(font, ch)
        sus = analyze(ours, ref)
        print(ch, "ink", int(ours.sum()), "ref_ink", int(ref.sum()), "suspects", len(sus), sus[:4])
