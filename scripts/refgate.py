#!/usr/bin/env python3
"""参考结构对比（**仅对比分析/研究，不是发布依据**）。

把成品字形与参考字体同字做组件级对比，找出「在参考结构里找不到对应墨迹」的组件，
用于人工研究污染/断笔来源。

口径（DECISIONS D20/D21）：
  - 参考字体 = 霞鹜文楷（OFL，`scripts/reffont.py`）；禁止系统宋体/黑体。
  - **对比结果不得用于自动删除字形组件**：破坏性清理开关已在主构建链禁用
    （`font_norm.vectorize_gray` 对 `enable_ref_filter` 直接 raise）。
  - 不数孔洞/连通分量作为质量判据：刻本断笔是工艺特征。
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from reffont import path as REF_FONT, index as REF_INDEX, has_char as _ref_has_char, raster as _ref_raster  # noqa: E402

SIZE = 256
DILATE = 5
MIN_AREA = 12          # 忽略极小噪点
COV_TH = 0.16          # 小碎片覆盖率阈值；大块另用 0.08
MAX_DEL_FRAC = 0.60    # 历史安全阀（仅报告用），主链禁用自动删除


def raster(font_path, ch, size=SIZE, index=None):
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype(font_path, size) if index is None else ImageFont.truetype(font_path, size, index=index)
    im = Image.new("L", (size, size), 0)
    ImageDraw.Draw(im).text((size // 2, int(0.88 * size)), ch, fill=255, font=f, anchor="ms")
    return np.array(im) > 127


def analyze(our_mask, ref_mask, dilate=DILATE, min_area=MIN_AREA, cov_th=COV_TH):
    """返回可疑组件列表（像素 bbox / 面积 / 参考覆盖率）。仅供人工分析。"""
    import cv2
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


def ref_has(ch):
    """参考字体是否收录该字（未收录 → 参考对比不适用，调用方须披露）。"""
    return _ref_has_char(ch)


def glyph_masks(our_font, ch, size=SIZE):
    ours = raster(our_font, ch, size)
    if not ref_has(ch):
        return ours, None
    return ours, _ref_raster(ch, size)


def safe_to_delete(suspects, total_ink, max_del_frac=MAX_DEL_FRAC):
    """历史安全阀（仅报告用）；主构建链禁止据此删除组件（D20）。"""
    del_area = sum(s["area"] for s in suspects)
    return del_area <= max_del_frac * max(1, total_ink)
