#!/usr/bin/env python3
"""C 流 · 字形归一化：300dpi crop -> 轮廓 -> EM1000 字面框（y 向上）。

链路（与 guangeti 06_norm.py / glyphvec.py 等价，去「写本」术语）：
  灰度 crop -> Otsu 二值化 -> 去碎片/贴边邻字 -> potrace 矢量化 ->
  等比缩放（最长边 = 760 units）-> 平移到 (500, 400) -> 写 glyph 记录

输出：
  work/font/glyphs.jsonl   每行 {char, contours, src, ...}
  work/font/glyphs/<char>.json

依赖 work/font/_pylibs（fontTools/potracer），不改 .venv。
"""



from __future__ import annotations


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
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work" / "font"
sys.path.insert(0, str(WORK / "_pylibs"))

PDF_DIR = ROOT / "康熙字典"
PDF_MAP = json.load(open(ROOT / "work" / "t2" / "pdf_map.json"))
DPI150_TO_PT = 72.0 / 150.0          # 150dpi 页面像素 -> PDF pt

EM = 1000
# 参考字体统一走 scripts/reffont.py（霞鹜文楷 OFL）；禁止系统宋体等专有字体（D21）。
# 注意：参考过滤属破坏性清理，主链已按 D20 禁用（vectorize_gray 会 raise）。
ASCENT = 880
DESCENT = -120
INK_LONG_SIDE = 760.0     # 字面框最长边 -> font units
INK_CX, INK_CY = 500.0, 400.0   # 字面框中心（基线 y=0 之上）
MIN_INK_PX = 120          # 太小/空 crop 直接拒
MIN_INK_AREA_RATIO = 0.02


# --------------------------------------------------------------------------- #
# 位图处理
# --------------------------------------------------------------------------- #
def binarize(gray: np.ndarray, thr_offset: int = -5) -> np.ndarray:
    """Otsu 二值化（刻本），v2.3：轻度中值去噪 + 阈值下移 5（去墨晕，保笔画直顺）。"""
    import cv2
    g = cv2.medianBlur(gray, 3)
    thr, _ = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thr = min(max(int(thr) + thr_offset, 60), 210)
    return g < thr


def clean_ink(ink: np.ndarray, min_area: int = 40,
              center: tuple[int, int, int, int] | None = None,
              border_margin: int = 1) -> np.ndarray:
    """去掉版框/栏线/邻字残片，保留字身成分（v11：solid-bbox 规则）。

    1) 主成分（面积最大）永远保留；
    2) 贴 crop 边的成分 -> 版框/栏线/邻字残片，丢；
    3) 「实心成分」= 短边 > thin_thr(14px) 的成分；取它们并集 bbox；
       细线成分（短边 <= thin_thr）若中心落在 solid bbox 外扩 8px 之外 -> 栏线/杂线，丢；
       落在 solid bbox 内 -> 字身细笔（撇/点/挑），保留；
    4) 极小碎片：落在主成分 bbox 内才留。
    """
    import cv2
    n, lab, stats, cent = cv2.connectedComponentsWithStats(ink.astype(np.uint8), 8)
    if n <= 1:
        return ink
    h, w = ink.shape
    X, Y, WW, HH, AR = 0, 1, 2, 3, 4
    thin_thr = 14
    main = 1 + int(np.argmax(stats[1:, AR]))
    mx, my = stats[main, X], stats[main, Y]
    mw, mh = stats[main, WW], stats[main, HH]

    box = None
    if center is not None:
        bx0, by0, bx1, by1 = center
        bw, bh = max(1, bx1 - bx0), max(1, by1 - by0)
        ex, ey = int(0.25 * bw), int(0.25 * bh)
        box = (bx0 - ex, by0 - ey, bx1 + ex, by1 + ey)

    solid = [i for i in range(1, n)
             if stats[i, AR] >= min_area and min(stats[i, WW], stats[i, HH]) > thin_thr]
    if main not in solid:
        solid.append(main)
    sx0 = min(stats[i, X] for i in solid)
    sy0 = min(stats[i, Y] for i in solid)
    sx1 = max(stats[i, X] + stats[i, WW] for i in solid)
    sy1 = max(stats[i, Y] + stats[i, HH] for i in solid)
    m = 8
    sx0, sy0, sx1, sy1 = sx0 - m, sy0 - m, sx1 + m, sy1 + m

    # 字身主笔画宽度（用于 v12b 边角料过滤）
    dt = cv2.distanceTransform(ink.astype(np.uint8), cv2.DIST_L2, 3)
    main_dt = dt[lab == main]
    stroke_w = float(np.median(main_dt)) * 2 if main_dt.size else 0.0
    main_area = float(stats[main, AR])

    keep = np.zeros(n, bool)
    for i in range(1, n):
        x, y = stats[i, X], stats[i, Y]
        ww, hh, area = stats[i, WW], stats[i, HH], stats[i, AR]
        if i == main:
            keep[i] = True
            continue
        border = (x <= border_margin or y <= border_margin
                  or x + ww >= w - border_margin or y + hh >= h - border_margin)
        if border:
            continue
        cx, cy = x + ww / 2.0, y + hh / 2.0
        if box is not None and not (box[0] <= cx <= box[2] and box[1] <= cy <= box[3]):
            continue          # 字身框外扩 25% 之外：邻字/栏线残片
        thin = min(ww, hh) <= thin_thr
        if thin and not (sx0 <= cx <= sx1 and sy0 <= cy <= sy1):
            continue
        # v12b：边角料（细、小、且不在主体 bbox 内）-> 丢
        in_main_bbox = (mx <= x and x + ww <= mx + mw and my <= y and y + hh <= my + mh)
        if (not in_main_bbox and area < max(min_area, 0.01 * main_area)
                and stroke_w > 0 and min(ww, hh) <= 0.5 * stroke_w):
            continue
        if area < min_area:
            inside_main = (mx <= x and x + ww <= mx + mw and my <= y and y + hh <= my + mh)
            if inside_main:
                keep[i] = True
            continue
        keep[i] = True
    if not keep.any():
        keep[main] = True
    return keep[lab]


def clean_cluster(ink: np.ndarray, dist: float = 20.0, margin: int = 4,
                  min_area: int = 30, box: tuple | None = None) -> np.ndarray:
    """主体联通簇裁切 v2.3：主成分 + 距其 bbox <= dist 的成分 = 字形簇；
    取簇 bbox（外扩 margin）作为字形 cell，簇外墨迹（邻字/注文/栏线）整体剔除。
    可修掉「注文块被当字身」「邻字斜笔穿框」等切分错误，并避免碎片撑大 bbox 导致字形变小。
    """
    import cv2
    n, lab, stats, cent = cv2.connectedComponentsWithStats(ink.astype(np.uint8), 8)
    if n <= 1:
        return ink
    X, Y, W, H, A = 0, 1, 2, 3, 4
    h, w = ink.shape
    # 主体选择：优先「包含 crop 中心（=映射框中心）」且面积够大的成分，
    # 避免把邻字/注文块/栏线误当字身（v2.3b，修 tiny 字形）
    # 主体选择 v2.3c：排除「细长贴边成分（栏线/邻字滑笔）」，在剩余成分中取面积最大者；
    # 若全部过细，再退回面积最大者，避免把细线当字身导致字形变窄。
    cand = []
    for i in range(1, n):
        x, y, ww, hh, a = (stats[i, X], stats[i, Y], stats[i, W], stats[i, H], float(stats[i, A]))
        if min(ww, hh) < 12 or a < 50:
            continue
        if max(ww, hh) / max(1, min(ww, hh)) > 6:   # 细长成分（栏线/滑笔）不作主体
            continue
        cand.append((a, i))
    if cand:
        main = max(cand)[1]
    else:
        main = 1 + int(np.argmax(stats[1:, A]))

    def bdist(i, j):
        xi, yi, wi, hi = stats[i, X], stats[i, Y], stats[i, W], stats[i, H]
        xj, yj, wj, hj = stats[j, X], stats[j, Y], stats[j, W], stats[j, H]
        dx = max(xj - (xi + wi), xi - (xj + wj), 0)
        dy = max(yj - (yi + hi), yi - (yj + hj), 0)
        return (dx * dx + dy * dy) ** 0.5

    incl = [main]
    for i in range(1, n):
        if i == main or stats[i, A] < min_area:
            continue
        x, y, ww, hh = stats[i, X], stats[i, Y], stats[i, W], stats[i, H]
        in_box = False
        if box is not None:
            bx0, by0, bx1, by1 = box
            ccx, ccy = cent[i]
            in_box = (bx0 <= ccx <= bx1) and (by0 <= ccy <= by1)
        if in_box or bdist(i, main) <= dist:
            incl.append(i)
    keep = np.isin(lab, incl)
    # safety valve：簇 bbox 若明显小于字身框（丢偏旁/被细线主导），退回「字身框内墨迹」
    if box is not None:
        bx0, by0, bx1, by1 = box
        cx0 = min(stats[i, X] for i in incl)
        cy0 = min(stats[i, Y] for i in incl)
        cx1 = max(stats[i, X] + stats[i, W] for i in incl)
        cy1 = max(stats[i, Y] + stats[i, H] for i in incl)
        cw, chh = cx1 - cx0, cy1 - cy0
        bw, bh = max(1, bx1 - bx0), max(1, by1 - by0)
        if cw < 0.55 * bw or chh < 0.55 * bh:
            out = np.zeros_like(ink)
            yy0, yy1 = max(0, by0 - margin), min(h, by1 + margin)
            xx0, xx1 = max(0, bx0 - margin), min(w, bx1 + margin)
            out[yy0:yy1, xx0:xx1] = ink[yy0:yy1, xx0:xx1]
            return out
    x0 = min(stats[i, X] for i in incl)
    y0 = min(stats[i, Y] for i in incl)
    x1 = max(stats[i, X] + stats[i, W] for i in incl)
    y1 = max(stats[i, Y] + stats[i, H] for i in incl)
    out = np.zeros_like(ink)
    yy0, yy1 = max(0, y0 - margin), min(h, y1 + margin)
    xx0, xx1 = max(0, x0 - margin), min(w, x1 + margin)
    out[yy0:yy1, xx0:xx1] = ink[yy0:yy1, xx0:xx1] & keep[yy0:yy1, xx0:xx1]
    return out


def trace(ink: np.ndarray, turdsize: int = 3, alphamax: float = 0.8,
          opttol: float = 0.2) -> list[dict]:
    """potrace 矢量化（位图 y 向下，像素坐标）。返回 [{start:[x,y], segs:[...]}]。"""
    import potrace
    try:
        p = potrace.Bitmap(~ink).trace(turdsize=turdsize, alphamax=alphamax,
                                       opticurve=True, opttolerance=opttol)
    except ValueError:
        p = potrace.Bitmap(~ink).trace(turdsize=turdsize, alphamax=alphamax,
                                       opticurve=False, opttolerance=opttol)
    contours = []
    for curve in p:
        segs = []
        for seg in curve:
            if type(seg).__name__ == "CornerSegment":
                segs.append(["L", float(seg.end_point.x), float(seg.end_point.y)])
            else:
                segs.append(["C", float(seg.c1.x), float(seg.c1.y),
                             float(seg.c2.x), float(seg.c2.y),
                             float(seg.end_point.x), float(seg.end_point.y)])
        if len(segs) >= 3:
            contours.append({"start": [float(curve.start_point.x), float(curve.start_point.y)],
                             "segs": segs})
    return contours


def scale_contours(contours: list[dict], factor: float) -> list[dict]:
    """把像素坐标轮廓整体缩放（用于超采样 tracing 还原到原分辨率）。"""
    out = []
    for c in contours:
        segs = []
        for s in c["segs"]:
            if s[0] == "L":
                segs.append(["L", s[1] * factor, s[2] * factor])
            else:
                segs.append(["C", s[1] * factor, s[2] * factor, s[3] * factor,
                             s[4] * factor, s[5] * factor, s[6] * factor])
        out.append({"start": [c["start"][0] * factor, c["start"][1] * factor], "segs": segs})
    return out


def trace_upscaled(ink: np.ndarray, factor: int = 2, turdsize: int = 3,
                   alphamax: float = 0.8, opttol: float = 0.2) -> list[dict]:
    """超采样 tracing（2x）以减少 potrace 像素方块口径导致的描迹偏移/肥瘦差。"""
    import cv2
    up = cv2.resize(ink.astype(np.uint8), None, fx=factor, fy=factor,
                    interpolation=cv2.INTER_NEAREST).astype(bool)
    cs = trace(up, turdsize=turdsize * factor * factor, alphamax=alphamax, opttol=opttol)
    return scale_contours(cs, 1.0 / factor)


def contour_points(c: dict) -> list[tuple[float, float]]:
    pts = [tuple(c["start"])]
    for s in c["segs"]:
        if s[0] == "L":
            pts.append((s[1], s[2]))
        else:
            pts.append((s[1], s[2]))
            pts.append((s[3], s[4]))
            pts.append((s[5], s[6]))
    return pts


# --------------------------------------------------------------------------- #
# 归一化到 EM
# --------------------------------------------------------------------------- #
def normalize(contours: list[dict], em: int = EM, long_side: float = INK_LONG_SIDE,
              cx: float = INK_CX, cy: float = INK_CY,
              bbox_override: tuple[float, float, float, float] | None = None) -> tuple[list[dict], dict]:
    """像素坐标（y 向下）-> EM units（y 向上）：等比缩放 + 居中。

    v0 口径：所有字共用「最长边 760 units」的字面框（无 base 字体逐字光学校正，
    见 docs/FONT-BUILD.md 已知缺陷）；扁平字（一/乙）按宽度归一，不会被拉高。
    """
    xs, ys = [], []
    for c in contours:
        for x, y in contour_points(c):
            xs.append(x)
            ys.append(y)
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if bbox_override is not None:
        # 用主簇 bbox 做缩放/居中，避免小碎片/邻墨把整字拉偏、缩小
        x0, y0, x1, y1 = (float(v) for v in bbox_override)
    w, h = max(1e-6, x1 - x0), max(1e-6, y1 - y0)
    scale = long_side / max(w, h)
    # 位图中心（像素，y 向下）-> 目标中心（EM，y 向上）
    mx = (x0 + x1) / 2.0
    my = (y0 + y1) / 2.0

    def fx(px: float) -> float:
        return (px - mx) * scale + cx

    def fy(py: float) -> float:
        return (my - py) * scale + cy

    out = []
    for c in contours:
        segs = []
        for s in c["segs"]:
            if s[0] == "L":
                segs.append(["L", fx(s[1]), fy(s[2])])
            else:
                segs.append(["C", fx(s[1]), fy(s[2]), fx(s[3]), fy(s[4]),
                             fx(s[5]), fy(s[6])])
        out.append({"start": [fx(c["start"][0]), fy(c["start"][1])], "segs": segs})
    info = {"scale": scale, "bbox_px": [x0, y0, x1, y1],
            "bbox_em": [fx(x0), fy(y1), fx(x1), fy(y0)]}
    return out, info


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
_DOC_CACHE: dict[str, object] = {}


def prune_edge_contours(contours: list[dict], ring: float = 0.10,
                       area_frac: float = 0.02) -> list[dict]:
    """删除「完全落在字形 bbox 外环(ring)内」的小轮廓（邻字/栏线碎片）。

    在 normalize 之后调用（EM 坐标）。孔洞在内部，不受影响；完整笔画面积大，也不受影响。
    """
    if len(contours) <= 1:
        return contours

    def pts(c):
        out = [tuple(c["start"])]
        for s in c["segs"]:
            if s[0] == "L":
                out.append((s[1], s[2]))
            else:
                out.extend([(s[1], s[2]), (s[3], s[4]), (s[5], s[6])])
        return out

    P = [pts(c) for c in contours]
    xs = [p[0] for ps in P for p in ps]
    ys = [p[1] for ps in P for p in ps]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = max(1e-6, x1 - x0), max(1e-6, y1 - y0)
    total = w * h
    mx, my = ring * w, ring * h

    def area(ps):
        a = 0.0
        for i in range(len(ps)):
            xa, ya = ps[i]
            xb, yb = ps[(i + 1) % len(ps)]
            a += xa * yb - xb * ya
        return abs(a) / 2.0

    keep = []
    for c, ps in zip(contours, P):
        cx0, cx1 = min(p[0] for p in ps), max(p[0] for p in ps)
        cy0, cy1 = min(p[1] for p in ps), max(p[1] for p in ps)
        a = area(ps)
        cw, chh = cx1 - cx0, cy1 - cy0
        thin = (min(cw, chh) < 0.035 * max(w, h)) and (max(cw, chh) > 0.10 * max(w, h))
        in_ring = ((cx1 <= x0 + mx) or (cx0 >= x1 - mx)
                   or (cy1 <= y0 + my) or (cy0 >= y1 - my))
        # 只删「贴边且线状」的栏线/框线残片；不再删普通小轮廓（会误删笔画/偏旁）
        if in_ring and thin and a < area_frac * total:
            continue
        # 墨点噪声：极小且极小的轮廓（<0.1% 面积且最长边<12 units）
        if a < 0.001 * total and max(cw, chh) < 12:
            continue
        keep.append(c)
    return keep or contours


def _open_pdf(pdf: str):
    """按 PDF 缓存 fitz.Document（16k 字构建时避免反复 open 14GB 文档）。"""
    import fitz
    doc = _DOC_CACHE.get(pdf)
    if doc is None:
        doc = fitz.open(PDF_DIR / PDF_MAP[pdf])
        _DOC_CACHE[pdf] = doc
    return doc


def render_pdf_crop(page_key: str, box: list, pad150: int = 6, dpi: int = 300) -> np.ndarray:
    """150dpi 页面坐标 box -> 300dpi 灰度 crop（PDF 原生分辨率直渲染，不插值放大）。"""
    import fitz
    pdf, pnum = page_key.split("_")
    x0, y0, x1, y1 = box
    doc = _open_pdf(pdf)
    page = doc[int(pnum) - 1]
    clip = fitz.Rect((x0 - pad150) * DPI150_TO_PT, (y0 - pad150) * DPI150_TO_PT,
                     (x1 + pad150) * DPI150_TO_PT, (y1 + pad150) * DPI150_TO_PT)
    pix = page.get_pixmap(dpi=dpi, clip=clip, colorspace=fitz.csGRAY)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()


def strip_border_lines(ink: np.ndarray, band: float = 0.18, min_len: float = 0.45,
                       max_thick: float = 0.10, report: list | None = None) -> np.ndarray:
    """移除「版面框线 / 注文引用框线」长直线组件。

    两类判据（任一命中即删）：
      A. 贴边带内：长边 > min_len×crop 长，厚度 < max_thick×crop；
      B. 全 crop 范围：线状（长边 > 0.35×crop，厚度 < 0.06×crop）且**与主墨迹不连通**
         （中心到主成分 bbox 的距离 > 4px）——例如 佇 旁边的竖版框线。
    主成分（最大连通域）永不删除；不碰与字身相连的笔画。
    """
    import cv2
    src = (ink > 0).astype(np.uint8)
    h, w = src.shape
    n, lab, st, _ = cv2.connectedComponentsWithStats(src, 8)
    if n <= 1:
        return ink
    areas = [(st[i, cv2.CC_STAT_AREA], i) for i in range(1, n)]
    main_i = max(areas)[1]
    mx0, my0 = st[main_i, cv2.CC_STAT_LEFT], st[main_i, cv2.CC_STAT_TOP]
    mx1 = mx0 + st[main_i, cv2.CC_STAT_WIDTH]
    my1 = my0 + st[main_i, cv2.CC_STAT_HEIGHT]
    out = src.copy()
    bx0, by0 = int(band * w), int(band * h)
    bx1, by1 = int((1 - band) * w), int((1 - band) * h)
    crop_long = max(w, h)
    for i in range(1, n):
        if i == main_i:
            continue
        x, y, ww, hh, a = st[i]
        cx, cy = x + ww / 2, y + hh / 2
        long_dim = max(ww, hh); thick = min(ww, hh)
        near_edge = cx < bx0 or cx > bx1 or cy < by0 or cy > by1
        rule_a = near_edge and long_dim >= min_len * crop_long and thick <= max_thick * crop_long
        # 到主成分 bbox 的距离
        dx = max(0, max(mx0, x) - min(mx1, x + ww))
        dy = max(0, max(my0, y) - min(my1, y + hh))
        isolated = (dx * dx + dy * dy) ** 0.5 > 4
        # B2：更宽松的「非边缘带」孤立线状残片（路 类，注文引用框/版框残段）
        straight = False
        if isolated and long_dim >= 0.25 * crop_long and thick <= 0.08 * crop_long:
            ys2, xs2 = np.nonzero(lab == i)
            if len(xs2) >= 2:
                pts = np.column_stack([xs2, ys2]).astype(np.float32)
                vx, vy, lx0, ly0 = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01).ravel()
                dev = np.abs((pts[:, 0] - lx0) * vy - (pts[:, 1] - ly0) * vx)
                straight = float(dev.max()) <= 1.6
        rule_b = straight
        if rule_a or rule_b:
            out[lab == i] = 0
            if report is not None:
                report.append({"area": int(a), "bbox": [int(x), int(y), int(x + ww), int(y + hh)],
                               "long": int(long_dim), "thick": int(thick),
                               "rule": "A" if rule_a else "B",
                               "isolated": bool(isolated)})
    return out.astype(ink.dtype)



def strip_straight_lines_swt(ink: np.ndarray, min_len_frac: float = 0.28,
                             max_halfwidth: float = 4.6, dilate: int = 3) -> np.ndarray:
    """删除「细长直线」像素（版框/栏线/引用框线）。

    思路：距离变换半宽 <= max_halfwidth 的像素为「细线候选」；用 Hough 找长直线
    （近轴、长度 > min_len_frac×crop），沿该线膨胀 dilate 后与细线候选求交 → 删除。
    不碰粗笔画（半宽 > max_halfwidth 的笔画像素不受影响）。
    """
    import cv2
    src = (ink > 0).astype(np.uint8)
    h, w = src.shape
    if h < 40 or w < 40:
        return ink
    dt = cv2.distanceTransform(src, cv2.DIST_L2, 5)
    thin = dt <= max_halfwidth
    lines = cv2.HoughLinesP(src * 255, 1, np.pi / 180, threshold=60,
                            minLineLength=int(min_len_frac * max(h, w)), maxLineGap=14)
    if lines is None:
        return ink
    erase = np.zeros_like(src)
    arr = lines.reshape(-1, 4)
    for xa, ya, xb, yb in arr[:24]:
        L = float(np.hypot(xb - xa, yb - ya))
        if L < min_len_frac * max(h, w):
            continue
        ang = abs(np.degrees(np.arctan2(yb - ya, xb - xa))) % 90
        if min(ang, 90 - ang) > 10:
            continue
        ln = np.zeros_like(src)
        cv2.line(ln, (int(xa), int(ya)), (int(xb), int(yb)), 1, 1)
        ln = cv2.dilate(ln, np.ones((2 * dilate + 1, 2 * dilate + 1), np.uint8))
        erase |= ln
    kill = (erase > 0) & thin
    if int(kill.sum()) == 0:
        return ink
    out = src.copy()
    out[kill] = 0
    return out.astype(ink.dtype)



def strip_edge_small_comps(ink: np.ndarray, box: tuple[float, float, float, float],
                           band: float = 0.18,
                           h_range: tuple[float, float] = (0.30, 0.62),
                           w_range: tuple[float, float] = (0.16, 0.78)) -> np.ndarray:
    """删除「字框外带区域内的小组件」（邻字/注文/页码残片类污染的类级修复）。

    依据版式：字头占 2×2 格块（box）；邻字/注文小字高度约为块高的 0.35–0.5，
    出现在块的**外带**（靠 cell 边界）。删除判据：中心在外带内 且 高 < 0.62×块高
    且 面积 < 3% 块内墨量。字形自身的孤立小笔画（点）靠近字心/主笔画，不受影响。
    """
    import cv2
    x0, y0, x1, y1 = [float(v) for v in box]
    bw, bh = max(1.0, x1 - x0), max(1.0, y1 - y0)
    src = (ink > 0).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(src, 8)
    if n <= 1:
        return ink
    out = src.copy()
    bx0, by0 = x0 + band * bw, y0 + band * bh
    bx1, by1 = x1 - band * bw, y1 - band * bh
    for i in range(1, n):
        x, y, ww, hh, a = [int(v) for v in st[i]]
        cx, cy = x + ww / 2, y + hh / 2
        in_band = cx < bx0 or cx > bx1 or cy < by0 or cy > by1
        if not in_band:
            continue
        # 只删「注文小字尺寸」的组件：高度/宽度都在注文字号区间内
        hf, wf = hh / bh, ww / bw
        if h_range[0] <= hf <= h_range[1] and w_range[0] <= wf <= w_range[1]:
            out[lab == i] = 0
        elif min(ww, hh) <= 4 and max(ww, hh) >= 0.12 * bw and a < 400:
            # 细直线残片（框线/栏线）：仅限很细且短、面积小的
            out[lab == i] = 0
    return out.astype(ink.dtype)



def strip_edge_fragments(ink: np.ndarray, box: tuple[float, float, float, float],
                         band: float = 0.06, max_area_frac: float = 0.009,
                         min_area: int = 80) -> np.ndarray:
    """删除「块边缘带内的小碎片」（邻字笔画尖端/点、框线残屑）。

    判据：组件面积 < max(min_area, max_area_frac×块内墨量) 且（高<13%块高 或 宽<25%块宽）
    且 bbox 与外带（block 外 6%）相交。字形自身的点面积更大、位置更靠内，不受影响。
    """
    import cv2
    x0, y0, x1, y1 = [float(v) for v in box]
    bw, bh = max(1.0, x1 - x0), max(1.0, y1 - y0)
    src = (ink > 0).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(src, 8)
    if n <= 1:
        return ink
    total = int(src.sum())
    ref_a = max(min_area, max_area_frac * total)
    out = src.copy()
    bx0, by0 = x0 + band * bw, y0 + band * bh
    bx1, by1 = x1 - band * bw, y1 - band * bh
    for i in range(1, n):
        x, y, ww, hh, a = [int(v) for v in st[i]]
        if a >= ref_a:
            continue
        flat = (hh < 0.13 * bh) or (ww < 0.25 * bw)
        if not flat:
            continue
        # bbox 与外带相交（贴 block 边）
        touches = (x < bx0) or (x + ww > bx1) or (y < by0) or (y + hh > by1)
        if touches:
            out[lab == i] = 0
    return out.astype(ink.dtype)



def erase_rects(ink: np.ndarray, rects: list[tuple[int, int, int, int]] | None) -> np.ndarray:
    """把指定矩形区域内的墨置零（用于清除版框线带：位置由页面级检测给出）。"""
    if not rects:
        return ink
    out = ink.copy()
    h, w = out.shape
    for (x0, y0, x1, y1) in rects:
        x0, y0 = max(0, int(x0)), max(0, int(y0))
        x1, y1 = min(w, int(x1)), min(h, int(y1))
        if x1 > x0 and y1 > y0:
            out[y0:y1, x0:x1] = 0
    return out




def trim_crop_frame_edges(ink: np.ndarray, max_band: int = 40) -> np.ndarray:
    """裁片级版面边排除（最后一层保险）：

    从裁片四边向内，若外带出现「贯穿裁片的长直线带」（框线在 crop 内的残余），
    则把该边整体裁掉（带 + 其后空白），直到遇到正文墨。只动**外带**，不碰字身。
    """
    out = ink.copy()
    h, w = out.shape
    def find_top():
        for y in range(min(max_band, h)):
            if out[y].mean() >= 0.55 and out[y].sum() >= 0.5 * w:
                return y
        return None
    def find_bot():
        for y in range(h - 1, max(0, h - max_band), -1):
            if out[y].mean() >= 0.55 and out[y].sum() >= 0.5 * w:
                return y
        return None
    def find_left():
        for x in range(min(max_band, w)):
            if out[:, x].mean() >= 0.55 and out[:, x].sum() >= 0.5 * h:
                return x
        return None
    def find_right():
        for x in range(w - 1, max(0, w - max_band), -1):
            if out[:, x].mean() >= 0.55 and out[:, x].sum() >= 0.5 * h:
                return x
        return None
    ytop = find_top()
    if ytop is not None:
        yy = ytop
        while yy + 1 < h and out[yy + 1].mean() < 0.05:
            yy += 1
        out[:yy + 1, :] = False
    ybot = find_bot()
    if ybot is not None:
        yy = ybot
        while yy - 1 >= 0 and out[yy - 1].mean() < 0.05:
            yy -= 1
        out[yy:, :] = False
    xleft = find_left()
    if xleft is not None:
        xx = xleft
        while xx + 1 < w and out[:, xx + 1].mean() < 0.05:
            xx += 1
        out[:, :xx + 1] = False
    xright = find_right()
    if xright is not None:
        xx = xright
        while xx - 1 >= 0 and out[:, xx - 1].mean() < 0.05:
            xx -= 1
        out[:, xx:] = False
    return out


def strip_frame_lines_crossing_block(ink: np.ndarray, block_rect=None) -> np.ndarray:
    """类级规则：块内「贯穿块且延伸到块外」的细线 = 框线/界行；删除。

    字身笔画不会延伸到块外，因此该规则对字身零误伤；不依赖页级框线检测。
    block_rect = (x0,y0,x1,y1) crop 坐标；None 时不处理。
    """
    if block_rect is None:
        return ink
    out = ink.copy()
    h, w = out.shape
    x0, y0, x1, y1 = [int(round(v)) for v in block_rect]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 - x0 < 10 or y1 - y0 < 10:
        return out
    gap = 8
    def extend_row(y):
        left = out[y, max(0, x0 - gap):x0].any()
        right = out[y, x1:min(w, x1 + gap)].any()
        return left or right
    def extend_col(x):
        up = out[max(0, y0 - gap):y0, x].any()
        down = out[y1:min(h, y1 + gap), x].any()
        return up or down
    for y in range(y0, y1):
        seg = out[y, x0:x1]
        if seg.mean() >= 0.80 and extend_row(y):
            out[y, x0:x1] = False
    for x in range(x0, x1):
        seg = out[y0:y1, x]
        if seg.mean() >= 0.80 and extend_col(x):
            out[y0:y1, x] = False
    return out

def strip_crop_frame_bands(ink: np.ndarray, frac: float = 0.85) -> np.ndarray:
    """裁片级框线排除（切前层，不是事后按形状删组件）：

    只删「贯穿整个裁片边界」的整行/整列墨带（真框线必然贯穿裁片；字形笔画不会触到裁片两侧），
    因此对字身零误伤。用于 content clip 之后仍残留的框线（框线正好穿过整个 crop 的情形）。
    """
    out = ink.copy()
    h, w = out.shape
    rows = []
    for y in range(h):
        row = out[y]
        if row[0] and row[-1] and row.sum() >= frac * w:
            rows.append(y)
    cols = []
    for x in range(w):
        col = out[:, x]
        if col[0] and col[-1] and col.sum() >= frac * h:
            cols.append(x)
    def erase_runs(idx, axis):
        if not idx:
            return
        runs = np.split(np.array(idx), np.where(np.diff(idx) > 1)[0] + 1)
        for r in runs:
            a, b = int(r[0]), int(r[-1])
            if axis == 0:
                out[a:b + 1, :] = False
            else:
                out[:, a:b + 1] = False
    erase_runs(rows, 0)
    erase_runs(cols, 1)
    return out

def mask_to_block(ink: np.ndarray, rect: tuple[int, int, int, int] | None) -> np.ndarray:
    """只保留 2×2 格块内的墨迹（格块=源头正确边界；块外一律不属于本字）。"""
    if rect is None:
        return ink
    x0, y0, x1, y1 = [int(v) for v in rect]
    out = np.zeros_like(ink)
    h, w = ink.shape
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 > x0 and y1 > y0:
        out[y0:y1, x0:x1] = ink[y0:y1, x0:x1]
    return out



def main_cluster_bbox(ink: np.ndarray, area_frac: float = 0.22):
    """主簇 bbox：面积 >= area_frac×最大组件的所有组件并集（排除小碎片/邻墨）。"""
    import cv2
    src = (ink > 0).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(src, 8)
    if n <= 1:
        return None
    areas = [(int(st[i, cv2.CC_STAT_AREA]), i) for i in range(1, n)]
    main_a = max(areas)[0]
    xs0, ys0, xs1, ys1 = [], [], [], []
    for a, i in areas:
        if a >= area_frac * main_a:
            x, y, ww, hh, _ = [int(v) for v in st[i]]
            xs0.append(x); ys0.append(y); xs1.append(x + ww); ys1.append(y + hh)
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def remove_specks(ink: np.ndarray, min_area: int = 14) -> np.ndarray:
    """剔除纸面墨点噪声（连通域面积 < min_area @300dpi；真实笔画/偏旁远大于此）。"""
    import cv2
    src = (ink > 0).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(src, 8)
    if n <= 1:
        return ink
    allow = np.zeros(n, dtype=bool)
    allow[1:] = st[1:, cv2.CC_STAT_AREA] >= min_area
    return allow[lab].astype(ink.dtype)



_REF_HAS = None


def _ref_has(ch: str) -> bool:
    global _REF_HAS
    if _REF_HAS is None:
        try:
            sys.path.insert(0, str(ROOT / "scripts"))
            from reffont import cmap as _ref_cmap
            _REF_HAS = _ref_cmap()
        except Exception as e:
            raise RuntimeError(f"参考字体不可用（霞鹜文楷 OFL / REF_FONT_PATH）：{e}。"
                               "不允许静默跳过参考过滤。")
    return ord(ch) in _REF_HAS


def apply_reference_filter(ink: np.ndarray, ch: str, dilate: int = 25,
                           cov_th: float = 0.20, max_drop_frac: float = 0.15) -> np.ndarray:
    """像素级参考过滤（类级修复）：删掉「参考字体同字没有对应墨迹」的组件。

    以参考字形按主组件配准（缩放+平移）后膨胀 15px 作为容差；覆盖率<0.35 且
    面积<主组件 25% 的组件删除。覆盖率低但面积大者保留（安全阀）。
    """
    import cv2
    if not ch or not _ref_has(ch):
        return ink
    h, w = ink.shape
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from reffont import raster as _ref_raster
        ref = _ref_raster(ch, 256)
    except Exception:
        return ink
    src = (ink > 0).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(src, 8)
    if n <= 1:
        return ink
    comps = []
    for i in range(1, n):
        x, y, ww, hh, a = [int(v) for v in st[i]]
        if a >= 12:
            comps.append((a, i, x, y, ww, hh))
    if not comps:
        return ink
    comps.sort(reverse=True)
    _, mi, mx, my, mw, mh = comps[0]
    rn, rlab, rst, _ = cv2.connectedComponentsWithStats(ref.astype(np.uint8), 8)
    rcomps = [(int(rst[j, cv2.CC_STAT_AREA]), j) for j in range(1, rn) if rst[j, cv2.CC_STAT_AREA] >= 12]
    if not rcomps:
        return ink
    rcomps.sort(reverse=True)
    _, rj = rcomps[0]
    rx, ry, rw, rh = (int(rst[rj, 0]), int(rst[rj, 1]), int(rst[rj, 2]), int(rst[rj, 3]))
    c1 = (mx + mw / 2.0, my + mh / 2.0); c2 = (rx + rw / 2.0, ry + rh / 2.0)
    l1 = float(max(mw, mh)); l2 = float(max(rw, rh))
    s = l2 / max(1.0, l1)
    M = np.array([[s, 0, c2[0] - s * c1[0]], [0, s, c2[1] - s * c1[1]]], np.float32)
    ref_warp = cv2.warpAffine(ref.astype(np.uint8), M, (w, h), flags=cv2.INTER_NEAREST)
    ref_d = cv2.dilate(ref_warp, np.ones((dilate, dilate), np.uint8)) > 0
    out = src.copy()
    total_area = sum(c[0] for c in comps)
    dropped = 0
    for a, i, x, y, ww, hh in comps:
        comp = (lab == i)
        if i == mi:
            continue
        cov = float((comp & ref_d).sum()) / max(1, a)
        if cov >= cov_th or a >= 0.25 * comps[0][0]:
            continue
        # 安全阀：累计删除量不超过字形墨量 max_drop_frac
        if dropped + a > max_drop_frac * total_area:
            continue
        out[comp] = 0
        dropped += a
    return out.astype(ink.dtype)


def vectorize_gray(gray: np.ndarray, long_side: float = INK_LONG_SIDE,
                   center: tuple[int, int, int, int] | None = None,
                   char: str | None = None, enable_line_swt: bool = False,
                   enable_ref_filter: bool = False,
                   normalize_main_cluster: bool = False,
                   enable_edge_strip: bool = False,   # 危险：默认关（D20）
                   block_rect: tuple[int, int, int, int] | None = None,
                   erase_rects_list: list[tuple[int, int, int, int]] | None = None,
                   frame_mask: "np.ndarray | None" = None,
                   clip_mask: "np.ndarray | None" = None,
                   strip_border: bool = True,
                   strip_report: dict | None = None,
                   block_band300: float = 0.0) -> dict:
    """灰度图 -> 归一化轮廓（font_norm 主链路）。center=crop 内字身框像素坐标。"""
    if enable_edge_strip or enable_line_swt or enable_ref_filter:
        # v2.4.16–19 P0 事故根因：这类「按尺寸/位置删组件」开关已禁用；
        # 任何新用途必须先通过内容缺失闸 + 缺件扫描双回归，再单独评审开启。
        raise RuntimeError("destructive cleaning options are disabled by policy (D20); "
                           "use block mask/frame mask instead")
    ink = binarize(gray)
    if clip_mask is not None:
        ink[~clip_mask] = False
    ink = trim_crop_frame_edges(ink)
    ink = strip_crop_frame_bands(ink)
    # 注意：strip_frame_lines_crossing_block 在块相位不稳的页会误伤字身（实测 35→60 回归），
    # 默认不启用；待格点相位校验通过后再按页启用。
    ink = erase_rects(ink, erase_rects_list)
    if frame_mask is not None:
        ink[frame_mask > 0] = 0
    ink = mask_to_block(ink, block_rect)
    if block_rect is not None and block_band300 > 0:
        # pre-cut：块边缘带排除（界行/栏线残段恰好压在 2×2 块边界上，
        # 几何上先挖掉窄带，替代「切后按形状删线」的 strip_border_lines）
        b = int(round(block_band300))
        x0, y0, x1, y1 = [int(v) for v in block_rect]
        hh, ww = ink.shape
        if b > 0:
            for yy0, yy1 in ((max(0, y0), min(hh, y0 + b)),
                             (max(0, y1 - b), min(hh, y1))):
                if yy1 > yy0:
                    ink[yy0:yy1, max(0, x0):min(ww, x1)] = False
            for xx0, xx1 in ((max(0, x0), min(ww, x0 + b)),
                             (max(0, x1 - b), min(ww, x1))):
                if xx1 > xx0:
                    ink[max(0, y0):min(hh, y1), xx0:xx1] = False
    ink = remove_specks(ink)
    if strip_border:
        _before = int(ink.sum())
        _removed = [] if strip_report is not None else None
        ink = strip_border_lines(ink, report=_removed)
        if strip_report is not None:
            _after = int(ink.sum())
            strip_report.update(before_px=_before, after_px=_after,
                                removed_px=_before - _after,
                                removed_frac=round((_before - _after) / max(1, _before), 4),
                                removed=_removed)
    if enable_line_swt:
        ink = strip_straight_lines_swt(ink)
    if enable_ref_filter and char:
        ink = apply_reference_filter(ink, char)
    if center is not None and enable_edge_strip:
        ink = strip_edge_small_comps(ink, center)
        ink = strip_edge_fragments(ink, center)
    ink = clean_cluster(ink, box=center)

    ink = clean_ink(ink, center=center)
    main_bb = main_cluster_bbox(ink) if normalize_main_cluster else None
    n_ink = int(ink.sum())
    if n_ink < MIN_INK_PX or n_ink < MIN_INK_AREA_RATIO * gray.size:
        return {"ok": False, "reason": f"ink too small ({n_ink})", "ink_px": n_ink}
    contours_px = trace_upscaled(ink, factor=2)
    if not contours_px:
        return {"ok": False, "reason": "potrace returned no contour", "ink_px": n_ink}
    contours, info = normalize(contours_px, long_side=long_side, bbox_override=main_bb)
    contours = prune_edge_contours(contours)
    n_segs = sum(len(c["segs"]) for c in contours)
    if n_segs < 4:
        return {"ok": False, "reason": f"degenerate contour ({n_segs} segs)", "ink_px": n_ink}
    return {"ok": True, "contours": contours, "n_contours": len(contours),
            "n_segs": n_segs, "ink_px": n_ink, "norm": info}


def vectorize_crop(crop_path: Path, long_side: float = INK_LONG_SIDE,
                   center: tuple[int, int, int, int] | None = None) -> dict:
    gray = np.array(Image.open(crop_path).convert("L"))
    return vectorize_gray(gray, long_side=long_side, center=center)


def vectorize_box(page_key: str, box: list, pads=(6, 18), long_side: float = INK_LONG_SIDE,
                  dpi: int = 300, char: str | None = None,
                  enable_line_swt: bool = False, enable_ref_filter: bool = False,
                  normalize_main_cluster: bool = False,
                  enable_edge_strip: bool = False,   # 危险：默认关
                  block150: tuple[float, float, float, float] | None = None,
                  erase150: list[tuple[int, int, int, int]] | None = None,
                  frame_mask: "np.ndarray | None" = None,
                  content_quad=None, strip_border: bool = True,
                  strip_report: dict | None = None,
                  block_edge_band150: float = 0.0,
                  frame_mask_outer: "np.ndarray | None" = None,
                  outer_keep_margin150: float = 4.0) -> dict:
    """150dpi box -> 灰度 crop -> 归一化轮廓（自适应 pad）。block150=2×2 格块（150dpi）。

    先按小 pad（6px@150dpi）渲染；若最大连通域触 crop 边界（说明框偏紧、
    字身被裁），自动加大 pad 重渲一次，避免丢字身笔画。
    """
    import cv2
    last = None
    for pad150 in pads:
        gray = render_pdf_crop(page_key, box, pad150=pad150, dpi=dpi)
        ink = binarize(gray)
        n, lab, stats, cent = cv2.connectedComponentsWithStats(ink.astype(np.uint8), 8)
        X, Y, WW, HH, AR = 0, 1, 2, 3, 4
        if n > 1:
            h, w = ink.shape
            big = [i for i in range(1, n) if stats[i, AR] >= 0.15 * stats[1:, AR].max()]
            clipped = False
            for i in big:
                x, y = stats[i, X], stats[i, Y]
                ww, hh = stats[i, WW], stats[i, HH]
                if x <= 1 or y <= 1 or x + ww >= w - 1 or y + hh >= h - 1:
                    clipped = True
                    break
        else:
            clipped = True
        pad_px = pad150 * 2      # 300dpi
        center = (pad_px, pad_px, gray.shape[1] - pad_px, gray.shape[0] - pad_px)
        block_rect = None
        erase_rects_crop = None
        if erase150:
            ox0 = (box[0] - pad150) * 2.0
            oy0 = (box[1] - pad150) * 2.0
            erase_rects_crop = [(int(round(x0 * 2 - ox0)), int(round(y0 * 2 - oy0)),
                                 int(round(x1 * 2 - ox0)), int(round(y1 * 2 - oy0)))
                                for (x0, y0, x1, y1) in erase150]
        if block150 is not None:
            ox = (box[0] - pad150) * 2.0
            oy = (box[1] - pad150) * 2.0
            block_rect = (int(round(block150[0] * 2.0 - ox)), int(round(block150[1] * 2.0 - oy)),
                          int(round(block150[2] * 2.0 - ox)), int(round(block150[3] * 2.0 - oy)))
        cm = None
        if content_quad is not None:
            import numpy as _np
            from page_frames import clip_mask_page as _clip
            cm = _clip(gray.shape, (box[0] - pad150, box[1] - pad150), content_quad, dpi_scale=2.0)
        fm = None
        if frame_mask is not None:
            import numpy as _np
            # box 为 float（150dpi 坐标）；frame_mask 是页坐标 int 网格，必须先取整再切片
            x0 = int(round(box[0] - pad150)); y0 = int(round(box[1] - pad150))
            mh, mw = frame_mask.shape
            sx0 = max(0, x0); sy0 = max(0, y0)
            sx1 = min(int(mw), x0 + gray.shape[1] // 2)
            sy1 = min(int(mh), y0 + gray.shape[0] // 2)
            if sx1 > sx0 and sy1 > sy0:
                sub = frame_mask[sy0:sy1, sx0:sx1]
                fm = cv2.resize(sub, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_NEAREST)
        if frame_mask_outer is not None:
            # 细短直线 mask（注文引文框/短界行段）：只应用在 keep 区之外，
            # keep 区 = 字身 box ± outer_keep_margin150；保护字头细笔画。
            mh2, mw2 = frame_mask_outer.shape
            ox0 = max(0, x0); oy0 = max(0, y0)
            ox1 = min(int(mw2), x0 + gray.shape[1] // 2)
            oy1 = min(int(mh2), y0 + gray.shape[0] // 2)
            if ox1 > ox0 and oy1 > oy0:
                sub2 = frame_mask_outer[oy0:oy1, ox0:ox1]
                fm2 = cv2.resize(sub2, (gray.shape[1], gray.shape[0]),
                                 interpolation=cv2.INTER_NEAREST)
                mm = int(round(outer_keep_margin150 * 2))
                # crop 坐标 = (page150 - (box - pad150)) * 2；keep 区 = box ± margin
                kx0 = max(0, int(round(2 * pad150)) - mm)
                ky0 = max(0, int(round(2 * pad150)) - mm)
                kx1 = min(gray.shape[1], int(round((box[2] - box[0] + pad150) * 2)) + mm)
                ky1 = min(gray.shape[0], int(round((box[3] - box[1] + pad150) * 2)) + mm)
                if kx1 > kx0 and ky1 > ky0:
                    fm2[ky0:ky1, kx0:kx1] = 0
                fm = fm2 if fm is None else np.maximum(fm, fm2)
        res = vectorize_gray(gray, long_side=long_side, center=center, char=char,
                             enable_line_swt=enable_line_swt,
                             enable_ref_filter=enable_ref_filter,
                             normalize_main_cluster=normalize_main_cluster,
                             enable_edge_strip=enable_edge_strip,
                             block_rect=block_rect,
                             erase_rects_list=erase_rects_crop,
                             frame_mask=fm, clip_mask=cm,
                             strip_border=strip_border, strip_report=strip_report,
                             block_band300=float(block_edge_band150) * 2.0)
        res["pad150"] = pad150
        res["clipped"] = bool(clipped)
        last = res
        if not clipped:
            return res
    return last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=str(WORK / "demo" / "manifest.json"),
                    help="字表 manifest（只处理 status=accept 的字）")
    ap.add_argument("--crops", default=str(WORK / "crops.json"),
                    help="crop 索引（font_curate.py crops 产出）")
    ap.add_argument("--out", default=str(WORK / "glyphs.jsonl"))
    ap.add_argument("--long-side", type=float, default=INK_LONG_SIDE)
    args = ap.parse_args()

    manifest = json.load(open(args.manifest))
    crops = {c["key"]: c for c in json.load(open(args.crops))}
    rows, bad = [], []
    for ch, m in sorted(manifest["chars"].items()):
        c = crops.get(m["key"])
        if c is None:
            bad.append({"char": ch, "key": m["key"], "reason": "crop 索引缺失"})
            continue
        crop_path = ROOT / c["crop"]
        if not crop_path.exists():
            bad.append({"char": ch, "key": m["key"], "reason": f"crop 不存在 {crop_path}"})
            continue
        center = None
        if c.get("crop_w") and c.get("crop_h"):
            pad_px = int(round(c.get("pad150", 18) * c.get("scale", 2.0)))
            center = (pad_px, pad_px, c["crop_w"] - pad_px, c["crop_h"] - pad_px)
        r = vectorize_crop(crop_path, long_side=args.long_side, center=center)
        if not r["ok"]:
            bad.append({"char": ch, "key": m["key"], "reason": r["reason"],
                        "ink_px": r.get("ink_px")})
            continue
        rows.append({"char": ch, "codepoint": f"U+{ord(ch):04X}",
                     "key": m["key"], "page": m["page"], "box": m["box"],
                     "layer": m.get("layer", ""), "label_source": m.get("label_source", ""),
                     "verified_by": m.get("verified_by", ""),
                     "n_contours": r["n_contours"], "n_segs": r["n_segs"],
                     "ink_px": r["ink_px"], "norm": r["norm"],
                     "contours": r["contours"]})
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    # 单字文件，便于人工抽查
    gdir = out.parent / "glyphs"
    gdir.mkdir(exist_ok=True)
    for r in rows:
        (gdir / f"{r['char']}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))
    stats = {"n_ok": len(rows), "n_bad": len(bad), "bad": bad,
             "n_contours_total": sum(r["n_contours"] for r in rows),
             "n_segs_total": sum(r["n_segs"] for r in rows)}
    (out.parent / "norm_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1))
    print(f"normalized: {len(rows)} ok, {len(bad)} bad -> {out}")
    for b in bad:
        print("  BAD", b)


if __name__ == "__main__":
    sys.exit(main())
