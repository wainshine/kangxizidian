#!/usr/bin/env python3
"""precut_masks.py — 与构建同口径的 pre-cut 掩膜（供扫描闸复用）。

背景（E24/E27/E29/E32）：字体构建在矢量化前会按页级直线 mask（长线+细线）、页级已验证线条带
（page_line_bands.json）、content quad 做 pre-cut 清零；而扫描闸（缺件/框线逃逸）只看
clip + 裁片外带，导致「构建已排除的框线/注文框线」被当作缺件/框线逃逸误报。
本模块把同一套 pre-cut 掩膜应用到扫描输入，使闸与构建口径一致（单一真源）。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _to_crop(mask, box, pad150, shape):
    """页 150dpi mask 网格 -> crop 300dpi bool 网格（None 原样返回）。"""
    if mask is None:
        return None
    import numpy as np
    import cv2
    h, w = shape
    x0 = int(round(box[0] - pad150))
    y0 = int(round(box[1] - pad150))
    sx0 = max(0, x0); sy0 = max(0, y0)
    sx1 = min(int(mask.shape[1]), x0 + w // 2)
    sy1 = min(int(mask.shape[0]), y0 + h // 2)
    if sx1 <= sx0 or sy1 <= sy0:
        return None
    sub = mask[sy0:sy1, sx0:sx1]
    return cv2.resize(sub, (w, h), interpolation=cv2.INTER_NEAREST) > 0


_MASK_CACHE = {}


def _page_masks(page):
    """页级 mask 每页只算一次（worker 内缓存；扫描是 per-char 循环）。"""
    global _MASK_CACHE
    if page not in _MASK_CACHE:
        import font_build as FB
        bands = FB.get_page_line_bands(page)
        _MASK_CACHE[page] = (FB.get_page_line_mask(page),
                             FB.get_page_thin_line_mask(page),
                             bands)
    return _MASK_CACHE[page]


def apply_precut_masks(ink, page, box, pad150=6, keep_margin150=2.0):
    """对 crop 二值 ink 应用构建同口径 pre-cut 掩膜（原地修改并返回）。

    - 页级长直线 mask：全局清零；
    - 页级已验证线条带（page_line_bands.json）：rect 内清零；
    - 页级细短直线 mask：只清零字身 keep 区（box±margin）之外。
    """
    ink = ink.copy()
    h, w = ink.shape

    lm_page, tm_page, bands_page = _page_masks(page)
    lm = _to_crop(lm_page, box, pad150, ink.shape)
    if lm is not None:
        ink[lm] = False

    for rec in bands_page:
        x0, y0, x1, y1 = [int(round(v)) for v in rec["rect"]]
        cx0 = int(round((x0 - (box[0] - pad150)) * 2))
        cy0 = int(round((y0 - (box[1] - pad150)) * 2))
        cx1 = int(round((x1 - (box[0] - pad150)) * 2))
        cy1 = int(round((y1 - (box[1] - pad150)) * 2))
        cx0 = max(0, cx0); cy0 = max(0, cy0)
        cx1 = min(w - 1, cx1); cy1 = min(h - 1, cy1)
        if cx1 >= cx0 and cy1 >= cy0:
            ink[cy0:cy1 + 1, cx0:cx1 + 1] = False

    tm = _to_crop(tm_page, box, pad150, ink.shape)
    if tm is not None:
        mm = int(round(keep_margin150 * 2))
        kx0 = max(0, int(round(2 * pad150)) - mm)
        ky0 = max(0, int(round(2 * pad150)) - mm)
        kx1 = min(w, int(round((box[2] - box[0] + pad150) * 2)) + mm)
        ky1 = min(h, int(round((box[3] - box[1] + pad150) * 2)) + mm)
        if kx1 > kx0 and ky1 > ky0:
            tm[ky0:ky1, kx0:kx1] = False
        ink[tm] = False
    return ink
