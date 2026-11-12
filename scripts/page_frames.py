#!/usr/bin/env python3
"""版框内正文区检测（切之前排除框线/页边黑带/角部）。

方法：
1) 估计页面微旋转 θ（Hough 长线段中位角，±4°，无则 0）；
2) 把页图按 -θ 旋转到「线轴对齐」空间；
3) 在旋转空间用「注文小字组件 bbox + 投影框线 + 页边黑带」求每个半版的 content box；
4) 返回原图坐标下的 content quad（旋转空间 box 的四角经逆变换回原图），裁切时按 quad 裁剪。
半版 content box 覆盖到框线内侧（含外扩半格覆盖字头），但**不包含框线与页边黑带**。
"""
import math
import numpy as np
import cv2


def _ink(gray):
    from detect_blocks import binarize
    return binarize(gray)


def _runs(idx):
    return np.split(idx, np.where(np.diff(idx) > 1)[0] + 1) if len(idx) else []


def estimate_skew(ink):
    h, w = ink.shape
    m8 = (ink.astype(np.uint8) * 255)
    lines = cv2.HoughLinesP(m8, 1, np.pi / 720, threshold=100,
                            minLineLength=int(0.25 * max(h, w)), maxLineGap=6)
    angs = []
    for x1, y1, x2, y2 in ([] if lines is None else lines.reshape(-1, 4)):
        L = math.hypot(x2 - x1, y2 - y1)
        if L < 0.25 * max(h, w):
            continue
        a = math.degrees(math.atan2(y2 - y1, x2 - x1))
        a = ((a + 90) % 180) - 90
        if 0.1 <= abs(a) <= 4:
            angs.append(a)
    if not angs:
        return 0.0
    return float(np.median(angs))


def _rot(ink, theta_deg):
    h, w = ink.shape
    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), theta_deg, 1.0)
    out = cv2.warpAffine(ink.astype(np.uint8) * 255, M, (w, h),
                         flags=cv2.INTER_NEAREST, borderValue=0)
    Minv = cv2.invertAffineTransform(M)
    return out, M, Minv


def _small_centers(ink, gutter):
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), 8)
    pts = {"L": [], "R": []}
    for i in range(1, n):
        x, y, ww, hh, a = [int(v) for v in st[i]]
        cx = x + ww / 2.0
        key = "L" if cx < gutter else "R"
        if 24 <= hh <= 54 and 9 <= ww <= 60 and 40 <= a <= 1200:
            pts[key].append((cx, y + hh / 2.0))
    return pts


def _line_positions(prof, thr=0.55):
    sm = np.convolve(prof, np.ones(3) / 3, mode="same")
    return [int((r[0] + r[-1]) / 2) for r in _runs(np.where(sm >= thr)[0])]


def _max_run(arr):
    idx = np.where(arr)[0]
    if len(idx) == 0:
        return 0
    return int(max([r[-1] - r[0] + 1 for r in _runs(idx)]))


def _long_rows(ink, x0, x1, y0, y1, min_frac=0.10, run_frac=0.15):
    """返回 y 行列表：行内最长连续墨段 ≥ run_frac*宽度 且行墨占比≥min_frac（细/断框线也覆盖）。"""
    W = max(1, x1 - x0)
    out = []
    for y in range(max(0, y0), min(ink.shape[0], y1)):
        row = ink[y, x0:x1]
        if row.mean() < min_frac:
            continue
        if _max_run(row) >= run_frac * W:
            # 孤立性：上下 5px 带墨占比低（框线两侧是空白；文字行/列不孤立）
            above = ink[max(0, y - 9):max(0, y - 3), x0:x1].mean() if y > 9 else 0.0
            below = ink[min(ink.shape[0], y + 3):min(ink.shape[0], y + 9), x0:x1].mean()
            if max(above, below) < 0.12:
                out.append(int(y))
    return out


def _long_cols(ink, x0, x1, y0, y1, min_frac=0.10, run_frac=0.15):
    """返回 x 列列表：列内最长连续墨段 ≥ run_frac*高度 且列墨占比≥min_frac。"""
    H = max(1, y1 - y0)
    out = []
    for x in range(max(0, x0), min(ink.shape[1], x1)):
        col = ink[y0:y1, x]
        if col.mean() < min_frac:
            continue
        if _max_run(col) >= run_frac * H:
            left = ink[y0:y1, max(0, x - 9):max(0, x - 3)].mean() if x > 9 else 0.0
            right = ink[y0:y1, min(ink.shape[1], x + 3):min(ink.shape[1], x + 9)].mean()
            if max(left, right) < 0.12:
                out.append(int(x))
    return out


def _edge_band(prof, side, min_frac=0.5, run_need=0.5):
    """页边黑带：返回该侧黑带的内边界（像素坐标）或 None。"""
    if side in ("left", "top"):
        idx = np.where(prof >= min_frac)[0]
        if len(idx) == 0:
            return None
        runs = _runs(idx)
        r = runs[0]
        if (r[-1] - r[0] + 1) < 4:
            return None
        return int(r[-1])
    else:
        idx = np.where(prof >= min_frac)[0]
        if len(idx) == 0:
            return None
        runs = _runs(idx)
        r = runs[-1]
        if (r[-1] - r[0] + 1) < 4:
            return None
        return int(r[0])


def detect_content_quads(gray):
    """返回 {half: {"box": (x0,y0,x1,y1) in rot space, "M": 2x3, "Minv": 2x3}}。

    box 内 = 正文区：取「最靠内且在小字 bbox 之外」的框线，再让 4px；
    页边黑带单独钳制。若检测不到框线，用「小字 bbox ± 26＋黑带钳制」兜底。
    """
    ink = _ink(gray)
    h, w = ink.shape
    colsum = ink.sum(axis=0).astype(np.float32)
    lo, hi = int(w * 0.42), int(w * 0.58)
    gutter = int(lo + np.argmin(colsum[lo:hi]))
    theta = estimate_skew(ink)
    if abs(theta) > 0.05:
        rot, M, Minv = _rot(ink, -theta)
    else:
        rot = (ink * 255).astype(np.uint8)
        M = np.array([[1, 0, 0], [0, 1, 0]], np.float32)
        Minv = M.copy()
    rotb = rot > 0
    small = _small_centers(rotb, gutter)
    out = {}
    for half, (hx0, hx1) in (("L", (0, gutter)), ("R", (gutter, w))):
        hx0, hx1 = int(max(0, hx0)), int(min(w, hx1))
        if hx1 - hx0 < 120:
            continue
        pts = small[half]
        if len(pts) < 50:
            continue
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        sx0, sx1 = min(xs), max(xs); sy0, sy1 = min(ys), max(ys)
        # 框线候选：只接受「在小字 bbox 之外」的长线（避免把文字行/列当框线）
        top_rows = [y for y in _long_rows(rotb, hx0, hx1, int(0.01 * h), int(max(0.01 * h, sy0 - 8)))
                    if y <= sy0 - 8]
        bot_rows = [y for y in _long_rows(rotb, hx0, hx1, int(min(h - 1, sy1 + 8)), int(h - 1))
                    if y >= sy1 + 8]
        y0 = sy0 - 60; y1 = sy1 + 60
        if top_rows:
            y0 = max(y0, max(top_rows) + 4)
        if bot_rows:
            y1 = min(y1, min(bot_rows) - 4)
        if y1 - y0 < 100:
            continue
        left_cols = [x for x in _long_cols(rotb, hx0, max(hx0 + 10, int(sx0 - 8)), int(y0), int(y1))
                     if x <= sx0 - 8]
        right_cols = [x for x in _long_cols(rotb, min(hx1 - 10, int(sx1 + 8)), hx1, int(y0), int(y1))
                      if x >= sx1 + 8]
        x0 = sx0 - 60; x1 = sx1 + 60
        if left_cols:
            x0 = max(x0, max(left_cols) + 4)
        if right_cols:
            x1 = min(x1, min(right_cols) - 4)
        # 页边黑带（在旋转空间近似：用全图投影的左右/上下带）
        colprof = rotb.mean(axis=0); rowprof = rotb.mean(axis=1)
        bl = _edge_band(colprof, "left"); br = _edge_band(colprof, "right")
        bt = _edge_band(rowprof, "top"); bb = _edge_band(rowprof, "bottom")
        if bl is not None and bl < sx0: x0 = max(x0, bl + 4)
        if br is not None and br > sx1: x1 = min(x1, br - 4)
        if bt is not None and bt < sy0: y0 = max(y0, bt + 4)
        if bb is not None and bb > sy1: y1 = min(y1, bb - 4)
        # 兜底：content 必须完整包住小字 bbox ± 8（防误裁）
        x0 = min(x0, sx0 - 8); x1 = max(x1, sx1 + 8)
        y0 = min(y0, sy0 - 8); y1 = max(y1, sy1 + 8)
        x0, y0 = max(0.0, x0), max(0.0, y0)
        x1, y1 = min(float(w - 1), x1), min(float(h - 1), y1)
        if x1 - x0 < 100 or y1 - y0 < 100:
            continue
        out[half] = {"box": (x0, y0, x1, y1), "M": M, "Minv": Minv,
                     "theta": round(theta, 3)}
    return out


def clip_mask_page(crop_shape, origin150, quad, dpi_scale=2.0):
    """crop (dpi_scale×150dpi) 像素 -> 原图150dpi -> 旋转空间 -> 是否在 box 内。"""
    if quad is None:
        return None
    x0r, y0r, x1r, y1r = quad["box"]; M = quad["M"]
    hh, ww = crop_shape
    ys, xs = np.mgrid[0:hh, 0:ww]
    px = origin150[0] + xs / dpi_scale + 0.5
    py = origin150[1] + ys / dpi_scale + 0.5
    rx = M[0, 0] * px + M[0, 1] * py + M[0, 2]
    ry = M[1, 0] * px + M[1, 1] * py + M[1, 2]
    inside = (rx >= x0r) & (rx <= x1r) & (ry >= y0r) & (ry <= y1r)
    return inside
