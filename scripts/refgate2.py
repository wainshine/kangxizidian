#!/usr/bin/env python3
"""参考结构闸 v2（带配准）：按最大组件配准（缩放+平移）后，再判其他组件在参考中是否有对应墨迹。"""
import os, sys
import numpy as np, cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from reffont import path as REF_FONT, index as REF_INDEX, raster as _ref_raster
SIZE = 256


def _cmaps():
    sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))
    return None


def raster(font_path, ch, size=SIZE, index=None):
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype(font_path, size) if index is None else ImageFont.truetype(font_path, size, index=index)
    im = Image.new("L", (size, size), 0)
    ImageDraw.Draw(im).text((size // 2, int(0.88 * size)), ch, fill=255, font=f, anchor="ms")
    return np.array(im) > 127


def _comps(mask):
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = [int(v) for v in st[i]]
        if a < 12:
            continue
        out.append({"id": i, "bbox": (x, y, x + w, y + h), "area": a})
    out.sort(key=lambda c: -c["area"])
    return lab, out


def analyze(our_mask, ref_mask, dilate=6, cov_th=0.25):
    lab_o, comps_o = _comps(our_mask)
    lab_r, comps_r = _comps(ref_mask)
    if not comps_o or not comps_r:
        return []
    mo = comps_o[0]; mr = max(comps_r, key=lambda c: c["area"])
    def center(b):
        return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)
    co, cr = center(mo["bbox"]), center(mr["bbox"])
    lo = max(mo["bbox"][2] - mo["bbox"][0], mo["bbox"][3] - mo["bbox"][1])
    lr = max(mr["bbox"][2] - mr["bbox"][0], mr["bbox"][3] - mr["bbox"][1])
    s = lr / max(1.0, lo)
    # 把 ours 映射到 ref 坐标系
    M = np.array([[s, 0, cr[0] - s * co[0]], [0, s, cr[1] - s * co[1]]], np.float32)
    ref_d = cv2.dilate(ref_mask.astype(np.uint8), np.ones((2 * dilate + 1, 2 * dilate + 1), np.uint8)) > 0
    total = int(our_mask.sum())
    out = []
    for c in comps_o:
        comp = (lab_o == c["id"]).astype(np.uint8)
        warp = cv2.warpAffine(comp, M, (SIZE, SIZE), flags=cv2.INTER_NEAREST)
        a = int(warp.sum())
        if a < 12:
            continue
        cov = float((warp & ref_d).sum()) / a
        small = c["area"] < 0.06 * total
        if cov < cov_th and small:
            out.append({"bbox": list(c["bbox"]), "area": c["area"], "cov": round(cov, 3)})
    return out


def masks(font, ch, size=SIZE):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from refgate import ref_has
    ours = raster(font, ch, size)
    if not ref_has(ch):
        return ours, None
    return ours, _ref_raster(ch, size)
