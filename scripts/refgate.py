#!/usr/bin/env python3
"""参考结构闸（语义锚）：把成品字形与参考字体同字做组件级对比，
找出「在参考结构里找不到对应墨迹」的组件（框线/邻字/碎片污染）。

标签（字）是语义锚：一个组件若是该字的部件，参考字体同字对应位置必有墨；
参考里没有 → 属于污染。风格差异用「参考墨迹膨胀 DILATE px」容忍。
"""
import json, os, sys
import numpy as np, cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SONGTI = "/System/Library/Fonts/Supplemental/Songti.ttc"
SIZE = 256
DILATE = 5
MIN_AREA = 12          # 忽略极小噪点
COV_TH = 0.16          # 小碎片覆盖率阈值；大块另用 0.08
MAX_DEL_FRAC = 0.60    # 安全阀：可疑组件面积合计不超过字形墨量 60% 才允许外科删除


def raster(font_path, ch, size=SIZE, index=None):
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype(font_path, size) if index is None else ImageFont.truetype(font_path, size, index=index)
    im = Image.new("L", (size, size), 0)
    ImageDraw.Draw(im).text((size // 2, int(0.88 * size)), ch, fill=255, font=f, anchor="ms")
    return np.array(im) > 127


def analyze(our_mask, ref_mask, dilate=DILATE, min_area=MIN_AREA, cov_th=COV_TH):
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
        small = a < 0.03 * max(1, total)
        if (cov < 0.16 and small) or (cov < 0.08):
            out.append({"bbox": [int(x), int(y), int(x + w), int(y + h)], "area": int(a),
                        "cov": round(cov, 3)})
    return out


_REF_CMAP = None


def ref_has(ch):
    """参考宋体是否收录该字（未收录 → 参考闸不适用）。"""
    global _REF_CMAP
    if _REF_CMAP is None:
        sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))
        from fontTools.ttLib import TTFont
        _REF_CMAP = TTFont(SONGTI, fontNumber=7).getBestCmap()
    return ord(ch) in _REF_CMAP


def glyph_masks(our_font, ch, size=SIZE):
    ours = raster(our_font, ch, size)
    if not ref_has(ch):
        return ours, None
    ref = raster(SONGTI, ch, size, index=7)
    return ours, ref


def safe_to_delete(suspects, total_ink, max_del_frac=MAX_DEL_FRAC):
    del_area = sum(s["area"] for s in suspects)
    return del_area <= max_del_frac * max(1, total_ink)
