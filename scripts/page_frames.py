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


def _edge_band(prof, side, min_frac=0.5):
    """页边黑带内边界（像素坐标）或 None。"""
    idx = np.where(prof >= min_frac)[0]
    if len(idx) == 0:
        return None
    runs = _runs(idx)
    if side in ("left", "top"):
        r = runs[0]
        return int(r[-1]) if (r[-1] - r[0] + 1) >= 4 else None
    r = runs[-1]
    return int(r[0]) if (r[-1] - r[0] + 1) >= 4 else None


def _hough_line_clusters(ink, theta_deg=0.0):
    """返回 (vclusters, hclusters)：近轴线聚类，每项 (pos, total_len, thickness)。"""
    h, w = ink.shape
    m8 = (ink.astype(np.uint8) * 255)
    lines = cv2.HoughLinesP(m8, 1, np.pi / 720, threshold=60,
                            minLineLength=int(0.12 * max(h, w)), maxLineGap=18)
    segs = [] if lines is None else lines.reshape(-1, 4)
    vs, hs = [], []
    for x1, y1, x2, y2 in segs:
        dx, dy = int(x2 - x1), int(y2 - y1)
        L = math.hypot(dx, dy)
        if L < 0.12 * max(h, w):
            continue
        a = math.degrees(math.atan2(dy, dx))
        ax = abs(((a + 45) % 90) - 45)
        if ax > 2.5:
            continue
        if abs(dy) <= abs(dx):
            hs.append(((y1 + y2) / 2.0, L))
        else:
            vs.append(((x1 + x2) / 2.0, L))
    def cluster(items, tol=8.0):
        if not items:
            return []
        items = sorted(items)
        out = []
        cur = [items[0]]
        for pos, L in items[1:]:
            if pos - cur[-1][0] <= tol:
                cur.append((pos, L))
            else:
                out.append((sum(p for p, _ in cur) / len(cur), sum(l for _, l in cur), len(cur)))
                cur = [(pos, L)]
        out.append((sum(p for p, _ in cur) / len(cur), sum(l for _, l in cur), len(cur)))
        return out
    return cluster(vs), cluster(hs)


def detect_content_quads(gray):
    """返回 {half: {"box": (x0,y0,x1,y1) in rot space, "M": 2x3, "Minv": 2x3}}。

    content box = 半版内「最靠内的框线簇」再让 4px；缺线侧用「小字 bbox±60 + 页边黑带」兜底。
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
    vcl, hcl = _hough_line_clusters(rotb)
    # 页边黑带（旋转空间近似）
    colprof = rotb.mean(axis=0); rowprof = rotb.mean(axis=1)
    bl = _edge_band(colprof, "left"); br = _edge_band(colprof, "right")
    bt = _edge_band(rowprof, "top"); bb = _edge_band(rowprof, "bottom")
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
        W = hx1 - hx0
        v_here = [(pos, L, n) for (pos, L, n) in vcl if hx0 <= pos <= hx1]
        h_here = [(pos, L, n) for (pos, L, n) in hcl]
        left_c = [pos for pos, L, n in v_here if pos <= sx0 - 6 and L >= 0.10 * h]
        right_c = [pos for pos, L, n in v_here if pos >= sx1 + 6 and L >= 0.10 * h]
        top_c = [pos for pos, L, n in h_here if pos <= sy0 - 6 and L >= 0.15 * W]
        bot_c = [pos for pos, L, n in h_here if pos >= sy1 + 6 and L >= 0.15 * W]
        x0 = sx0 - 60; x1 = sx1 + 60; y0 = sy0 - 60; y1 = sy1 + 60
        if left_c:
            x0 = max(x0, max(left_c) + 4)
        if right_c:
            x1 = min(x1, min(right_c) - 4)
        if top_c:
            y0 = max(y0, max(top_c) + 4)
        if bot_c:
            y1 = min(y1, min(bot_c) - 4)
        if bl is not None and bl < sx0: x0 = max(x0, bl + 4)
        if br is not None and br > sx1: x1 = min(x1, br - 4)
        if bt is not None and bt < sy0: y0 = max(y0, bt + 4)
        if bb is not None and bb > sy1: y1 = min(y1, bb - 4)
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
