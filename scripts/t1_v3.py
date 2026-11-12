#!/usr/bin/env python3
"""T1 v2 · 字头候选检测器（以「每半版字头数」为验收目标）

相对 v1.6 的定位变化（docs/TAKEOVER.md §1.2、§2C）：
  v1.6 输出「切格框」，precision 不是验收项（0.42-0.43）；
  v2 输出**每半版有序候选 + 类别分数**，验收 = 字头 recall ≥99.5% 且
  每半版「字头数」完全正确率 ≥95%（其余 |Δ|≤1）——计数是 v3 的命门。

候选来源（宁多勿少）：
  P1 v1.6 提案（腐蚀/膨胀 + refine_v3 紧化 + 方形度补并）
  P2 v1.6 框内最大连通域（把 v1.6 的「粘连大框」拆回单字形）
  P3 原墨连通域直接提案（字头尺寸带 / 扁平细笔画 / 竖长窄字 / 贴页缘）
  合并：按「字形质量」优先去重（不是按面积），避免大框吃掉真字头。

类别（cls 每类均给分数）：
  headword 字头 / guwen 古文大字变体 / title 标题块（卷首九字/TOC）
  ring 圈字（印刷圆圈+增/画数）/ glue 注文粘连（双字竖排等）
  margin 书眉·版心·边角料

古文判别要点（docs/TAKEOVER.md §5、Lead 2026-11-08 实测）：
  古文变体与字头**同尺寸级**（实测 sr 1.9-2.3，不是 1.7-1.8！），
  唯一可靠特征 = 阅读序紧邻其前的两小字「古文」标签，且标签之前是字头。
  故 guwen = 找到「[大字][古文两小字][大字]」三元组后标记最后一个大字。

用法：
  .venv/bin/python scripts/t1_v2.py --pdf 01 --pages 6-40 --dpi 300 --out work/detect2/boxes
  .venv/bin/python scripts/t1_v2.py --pdf 01 --pages 6-40 --dpi 150 \
      --page-dir work/t00/pages --out work/detect2/boxes150 --montage work/detect2/montage
"""
import argparse
import json
import math
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import cv2

cv2.setNumThreads(1)
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(ROOT, "康熙字典")
T00 = os.path.join(ROOT, "work", "t00")

# 版面先验（150dpi 实测，见 docs/PROBE.md §2；其他 dpi 按 s 缩放）
H0_PRIOR = 37.0          # 注文小字高（282 页实测 36-38）
BIN_T = 150              # 透印灰度 ~180，可干净分离
HEAD_SR = (1.72, 2.55)   # 字头高/注文高（金标 1.95-2.19，放宽留余量）
FLAT_SR = (0.10, 0.85)   # 一/乙/亅 类扁平字头：高度小，按宽度
FLAT_WR = (1.45, 3.60)
GUWEN_SR = (1.40, 2.75)  # 古文变体与字头同尺寸级（实测）


# ----------------------------------------------------------------------------
# 图像 / 版面
# ----------------------------------------------------------------------------
def page_ink(ink, s=1.0):
    """去掉长直线（版框/折缝）后的残墨。ink 为 uint8 0/1。"""
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(3, int(round(200 * s)))))
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, int(round(200 * s))), 1))
    v = cv2.morphologyEx(ink, cv2.MORPH_OPEN, vk)
    h = cv2.morphologyEx(ink, cv2.MORPH_OPEN, hk)
    return cv2.subtract(cv2.subtract(ink, v), h)


def components(ink_res, amin=1):
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink_res, 8, cv2.CV_32S)
    out = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a >= amin:
            out.append((int(x), int(y), int(w), int(h), int(a)))
    return out


def estimate_h0(comps, s):
    """注文小字高 h0：方格状小分量的高度中位数。"""
    hs = []
    amin = 40 * s * s
    for x, y, w, h, a in comps:
        if a < amin or not (25 * s <= h <= 65 * s):
            continue
        if 0.35 <= w / max(1, h) <= 2.8:
            hs.append(h)
    if len(hs) < 40:
        return H0_PRIOR * s
    h0 = float(np.median(hs))
    if not (0.85 * H0_PRIOR * s <= h0 <= 1.25 * H0_PRIOR * s):
        h0 = H0_PRIOR * s
    return h0


def hline_band(raw_ink, s):
    """版框上/下横线 → 正文 y 带。"""
    H, W = raw_ink.shape
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(5, int(400 * s)), 1))
    h = cv2.morphologyEx(raw_ink, cv2.MORPH_OPEN, hk)
    n, _, st, _ = cv2.connectedComponentsWithStats(h, 8)
    cand = []
    for i in range(1, n):
        x, y, w, hh, a = st[i]
        if w >= 0.30 * W:
            cand.append((int(y), int(y + hh)))
    y0 = min((c[0] for c in cand if c[0] < 0.32 * H), default=int(0.20 * H))
    y1 = max((c[1] for c in cand if c[1] > 0.82 * H), default=int(0.90 * H))
    if not (0.10 * H < y0 < 0.35 * H):
        y0 = int(0.20 * H)
    if not (0.80 * H < y1 < 0.95 * H):
        y1 = int(0.90 * H)
    return int(y0), int(y1)


def vline_count(raw_ink, y0, y1, x0, x1, s, maxrun=None):
    """正文带内「长竖线」（列界/版框/TOC 栏线）列数。TOC 页有很多，正文页 ~0-2。"""
    bh = y1 - y0
    if maxrun is None:
        band = (raw_ink[y0:y1] > 0)
        run = np.zeros(raw_ink.shape[1], np.int32)
        maxrun = np.zeros(raw_ink.shape[1], np.int32)
        for y in range(bh):
            run = (run + 1) * band[y]
            np.maximum(maxrun, run, out=maxrun)
    thr = int(0.25 * bh)
    thr_full = int(0.55 * bh)
    xs = np.where(maxrun[x0:x1] >= thr)[0] + x0
    if len(xs) == 0:
        return 0, 0, []
    groups = []
    for x in xs:
        if groups and x - groups[-1][-1] <= 3:
            groups[-1].append(int(x))
        else:
            groups.append([int(x)])
    n_full = sum(1 for g in groups if max(maxrun[x] for x in g) >= thr_full)
    return len(groups), int(n_full), [(g[0], g[-1]) for g in groups]


def col_maxrun(raw_ink, y0, y1):
    """每列在正文带内的最长连续墨竖线长度（版框/版心竖线远大于文字列）。"""
    band = (raw_ink[y0:y1] > 0)
    W = band.shape[1]
    bh = band.shape[0]
    run = np.zeros(W, np.int32)
    maxrun = np.zeros(W, np.int32)
    for y in range(bh):
        run = (run + 1) * band[y]
        np.maximum(maxrun, run, out=maxrun)
    return maxrun, bh


def strip_borders(raw_ink, y0, y1, s, W, split, maxrun=None):
    """版心（书眉）条内边界 x：L 半版返回右边界的 x，R 半版返回左边界的 x。

    版心条 = 页外缘的窄条，内含书眉小字；其内边界是一条长竖线（版框/版心线）。
    用「列最长竖线长度」找：外缘 2%-12% 区域内最长且非页缘黑带的那条线。
    找不到时退化为固定比例。
    """
    if maxrun is None:
        maxrun, bh = col_maxrun(raw_ink, y0, y1)
    else:
        bh = y1 - y0
    lo_ok, hi_ok = 0.12 * bh, 0.92 * bh
    # L：x ∈ [0.02, 0.12]*split
    a, b = int(0.02 * split), int(0.12 * split)
    best, bestx = 0, None
    for x in range(a, b):
        v = int(maxrun[x])
        if lo_ok <= v <= hi_ok and v > best:
            best, bestx = v, x
    xL = bestx if bestx is not None else int(0.045 * split)
    # R：x ∈ [W-0.12*(W-split), W-0.02*(W-split)]
    hw = W - split
    a, b = int(W - 0.12 * hw), int(W - 0.02 * hw)
    best, bestx = 0, None
    for x in range(a, b):
        v = int(maxrun[x])
        if lo_ok <= v <= hi_ok and v > best:
            best, bestx = v, x
    xR = bestx if bestx is not None else int(W - 0.045 * hw)
    return int(xL), int(xR)


# 模板（work/detect2/templates/*.png，取自 01_0006 目检框；150dpi）
_TEMPLATES = None


def load_templates():
    global _TEMPLATES
    if _TEMPLATES is not None:
        return _TEMPLATES
    d = os.path.join(ROOT, "work", "detect2", "templates")
    T = {}
    for n in ("kang", "dian", "gu", "wen"):
        p = os.path.join(d, n + ".png")
        if os.path.exists(p):
            im = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
            if im is not None:
                T[n] = im
    _TEMPLATES = T
    return T


def ncc_same_shape(a_gray, b_gray):
    """两灰度块的归一化互相关（统一到 a 的形状）。"""
    if b_gray.shape != a_gray.shape:
        b_gray = cv2.resize(b_gray, (a_gray.shape[1], a_gray.shape[0]),
                            interpolation=cv2.INTER_AREA)
    x = a_gray.astype(np.float32)
    y = b_gray.astype(np.float32)
    x -= x.mean()
    y -= y.mean()
    d = (np.linalg.norm(x) * np.linalg.norm(y))
    return float((x * y).sum() / d) if d > 1e-6 else 0.0


def match_layer(gray, dpi):
    """返回 150dpi 等比例灰度（模板匹配用）。"""
    s = dpi / 150.0
    if abs(s - 1.0) < 1e-6:
        return gray
    h = int(round(gray.shape[0] / s))
    w = int(round(gray.shape[1] / s))
    return cv2.resize(gray, (w, h), interpolation=cv2.INTER_AREA)


def find_title_block(gray, dpi, h0_150):
    """模板匹配「康」「典」找标题块，返回 150dpi 坐标下的标题块 bbox 列表。"""
    T = load_templates()
    if "kang" not in T or "dian" not in T:
        return []
    g = match_layer(gray, dpi)
    blocks = []
    for key in ("kang", "dian"):
        t = T[key]
        r = cv2.matchTemplate(g, t, cv2.TM_CCOEFF_NORMED)
        thr = 0.60
        for _ in range(3):
            mn, mx, mnl, mxl = cv2.minMaxLoc(r)
            if mx < thr:
                break
            x, y = mxl
            tw, th = t.shape[1], t.shape[0]
            blocks.append((key, x, y, tw, th, round(mx, 3)))
            yy0 = max(0, y - th // 2)
            yy1 = min(r.shape[0], y + th // 2)
            xx0 = max(0, x - tw // 2)
            xx1 = min(r.shape[1], x + tw // 2)
            r[yy0:yy1, xx0:xx1] = -1
    # 合并成标题块 bbox：康在其首列顶部；块 = 康左侧 ~6h0、下方 ~10.5h0
    zones = []
    h0 = h0_150
    for key, x, y, tw, th, sc in blocks:
        if key != "kang":
            continue
        zones.append([x - 6.2 * h0, y - 1.5 * h0, x + 2.6 * h0, y + 10.8 * h0])
    # 没有康、只有典（极少）→ 以典为锚
    if not zones:
        for key, x, y, tw, th, sc in blocks:
            if key == "dian":
                zones.append([x - 6.2 * h0, y - 10.0 * h0, x + 2.6 * h0, y + 2.0 * h0])
    return zones


def charmask_sim(tmpl_gray, crop_gray, thr=BIN_T, size=24):
    """二值字形相似度（统一 24x24 掩膜后零均值相关）。对轻微缩放/位移稳健。"""
    a = (tmpl_gray <= thr).astype(np.float32)
    b = (crop_gray <= thr).astype(np.float32)
    a = cv2.resize(a, (size, size), interpolation=cv2.INTER_AREA).ravel()
    b = cv2.resize(b, (size, size), interpolation=cv2.INTER_AREA).ravel()
    a -= a.mean()
    b -= b.mean()
    d = np.linalg.norm(a) * np.linalg.norm(b)
    return float(a.dot(b) / d) if d > 1e-6 else 0.0


def match_char_ncc(win_gray, tmpl_gray, s=1.0):
    """多尺度模板匹配（返回最佳 NCC）。窗口为待检字邻域，模板为 150dpi 字形。"""
    best = -1.0
    for sc0 in (0.80, 0.85, 0.90, 0.95, 1.0, 1.05, 1.10, 1.15, 1.20):
        sc = sc0 * s
        t = tmpl_gray if abs(sc - 1.0) < 1e-6 else cv2.resize(
            tmpl_gray, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
        if t.shape[0] > win_gray.shape[0] or t.shape[1] > win_gray.shape[1]:
            continue
        r = cv2.matchTemplate(win_gray, t, cv2.TM_CCOEFF_NORMED)
        best = max(best, float(r.max()))
    return best


def propose_chains(comp, h0, s, y0=None, y1=None):
    """竖向链合并：把被拆开的多笔画字头（二/三/亖/上 的横笔+主体）合成一个字头框。

    链 = 同列相邻的「大字块」或「宽扁笔」；合并后高 1.7-2.8h0、宽 1.2-3.0h0
    才接受。返回 (merged_boxes, consumed_comp_index_set)。
    """
    big, flat = [], []
    for i, (x, y, w, h, a) in enumerate(comp):
        sr, wr = h / h0, w / h0
        cy = y + h / 2
        if y0 is not None and (cy < y0 + 1.0 * h0 or cy > y1 - 1.0 * h0):
            continue   # 上下框带残段不参与链合并
        if a >= 300 * s * s and 1.30 <= sr <= 2.95 and 0.20 <= wr <= 2.95:
            big.append((i, x, y, w, h, "big"))
        elif a >= 140 * s * s and 0.06 <= sr <= 0.92 and 1.38 <= wr <= 3.60:
            flat.append((i, x, y, w, h, "flat"))
    items = sorted(big + flat, key=lambda t: t[1] + t[3] / 2)
    cols = []
    for it in items:
        cx = it[1] + it[3] / 2
        if cols and abs(cx - cols[-1]["cx"]) <= 0.85 * h0:
            cols[-1]["items"].append(it)
            n = len(cols[-1]["items"])
            cols[-1]["cx"] += (cx - cols[-1]["cx"]) / n
        else:
            cols.append({"cx": cx, "items": [it]})
    merged, consumed = [], set()
    for c in cols:
        chain = sorted(c["items"], key=lambda t: t[2])
        cur = []
        for it in chain:
            if not cur:
                cur = [it]
                continue
            prev = cur[-1]
            gap = it[2] - (prev[2] + prev[4])
            if gap <= 0.62 * h0:
                cur.append(it)
            else:
                if len(cur) >= 2:
                    _finish_chain(cur, merged, consumed, h0)
                cur = [it]
        if len(cur) >= 2:
            _finish_chain(cur, merged, consumed, h0)
    return merged, consumed


def _finish_chain(cur, merged, consumed, h0):
    x0 = min(t[1] for t in cur)
    y0 = min(t[2] for t in cur)
    x1 = max(t[1] + t[3] for t in cur)
    y1 = max(t[2] + t[4] for t in cur)
    w, h = x1 - x0, y1 - y0
    if not (1.65 * h0 <= h <= 2.85 * h0 and 1.15 * h0 <= w <= 3.05 * h0):
        return
    merged.append([int(x0), int(y0), int(x1), int(y1)])
    for t in cur:
        consumed.add(t[0])


def ink_mass_box(ink_res, x_lo, x_hi, y_lo, y_hi, h0, s, pad=4):
    """区域内墨块 bbox（小核膨胀合并断笔后取最大分量）——碎片字形的定位兜底。"""
    H, W = ink_res.shape
    x_lo = max(0, int(x_lo)); x_hi = min(W, int(x_hi))
    y_lo = max(0, int(y_lo)); y_hi = min(H, int(y_hi))
    if x_hi - x_lo < 3 or y_hi - y_lo < 3:
        return None
    sub = ink_res[y_lo:y_hi, x_lo:x_hi]
    dil = cv2.dilate(sub, cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                                    (int(9 * s) | 1, int(9 * s) | 1)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(dil, 8)
    best = None
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a >= 150 * s * s and (best is None or a > best[0]):
            best = (a, int(x), int(y), int(w), int(h))
    if best is None:
        return None
    return [x_lo + best[1] - pad, y_lo + best[2] - pad,
            x_lo + best[1] + best[3] + pad, y_lo + best[2] + best[4] + pad]


def fragment_union_box(ink_res, comps, x0, x1, y0, y1, h0, s, pad=2):
    """竖条区域内「最上面一个字」的碎片并集框（去掉长线/小点后合并）。"""
    cand = []
    for (x, y, w, h, a) in comps:
        cx = x + w / 2
        cy = y + h / 2
        if not (x0 <= cx <= x1 and y0 <= cy <= y1):
            continue
        if h > 3.2 * h0 or w > 3.2 * h0:
            continue
        if min(w, h) <= 2 or a < 40 * s * s:
            continue
        if a < 80 * s * s:
            continue
        cand.append((y, x, x + w, y + h))
    if not cand:
        return None
    cand.sort()
    top = cand[0][0]
    xs0 = [c[1] for c in cand if c[0] <= top + 1.30 * h0]
    xs1 = [c[2] for c in cand if c[0] <= top + 1.30 * h0]
    ys1 = [c[3] for c in cand if c[0] <= top + 1.30 * h0]
    box = [int(min(xs0)) - pad, int(top) - pad, int(max(xs1)) + pad, int(max(ys1)) + pad]
    return box


def find_guwen_labels(gray, ink_res, comps, h0, s, ctx, side):
    """找「[大字][古文小字对][大字]」三元组，返回 (guwen_boxes, labels)。

    guwen_boxes: 需要判 guwen 的候选 bbox（工作分辨率坐标）
    labels: [(cx, y0, y1, ncc_gu, ncc_wen)] 便于审计
    """
    T = load_templates()
    have_t = "gu" in T and "wen" in T
    H, W = ink_res.shape
    x_lo, x_hi = ctx["x_text"]
    by0, by1 = ctx["y0"], ctx["y1"]
    small, big = [], []
    for x, y, w, h, a in comps:
        cx = x + w / 2
        if not (x_lo - 6 * h0 <= cx <= x_hi + 6 * h0):
            continue
        cy = y + h / 2
        if not (by0 - 0.8 * h0 <= cy <= by1 + 0.8 * h0):
            continue
        if 0.50 * h0 <= h <= 1.35 * h0 and 0.32 * h0 <= w <= 1.50 * h0 and a >= 35 * s * s:
            small.append((cx, y, y + h, w, h, x))
        elif (1.40 * h0 <= h <= 2.95 * h0 and 0.28 * h0 <= w <= 2.95 * h0 and a >= 300 * s * s) or                 (FLAT_SR[0] * h0 <= h <= FLAT_SR[1] * h0 and FLAT_WR[0] * h0 <= w <= FLAT_WR[1] * h0
                 and a >= 180 * s * s):
            big.append((cx, y, y + h, w, h, x))
    if len(small) < 2 or not big:
        return [], []
    small.sort(key=lambda t: t[0])
    cols = []
    for it in small:
        if cols and abs(it[0] - cols[-1]["cx"]) <= 0.55 * h0:
            cols[-1]["items"].append(it)
            n = len(cols[-1]["items"])
            cols[-1]["cx"] += (it[0] - cols[-1]["cx"]) / n
        else:
            cols.append({"cx": it[0], "items": [it]})
    res, labels = [], []
    for c in cols:
        items = sorted(c["items"], key=lambda t: t[1])
        for i in range(len(items) - 1):
            a1, b1 = items[i], items[i + 1]
            pitch = b1[1] - a1[1]
            gap = b1[1] - a1[2]
            if not (0.85 * h0 <= pitch <= 1.45 * h0 and gap <= 0.60 * h0):
                continue
            # 标签前一个大字（同列上方；或列底 wrap 到右列顶）
            prev_ok = False
            for G in big:
                if abs(G[0] - a1[0]) <= 0.80 * h0 and G[2] <= a1[1] and a1[1] - G[2] <= 1.15 * h0:
                    prev_ok = True
                    break
            if not prev_ok:
                for G in big:
                    dx = G[0] - a1[0]
                    if 0.4 * h0 <= dx <= 2.6 * h0 and G[2] >= by1 - 2.2 * h0 and                             a1[1] <= by0 + 1.40 * h0:
                        prev_ok = True
                        break
            if not prev_ok:
                continue
            # 二值模板校验「古」「文」
            ncc_g = ncc_w = None
            if have_t:
                def crop_ch(it):
                    cx, yy0, yy1, ww, hh, xx0 = it
                    m = int(max(0.35 * h0, 10 * s))
                    X0 = max(0, int(xx0) - m)
                    X1 = min(W, int(xx0) + int(round(ww)) + m)
                    Y0 = max(0, int(yy0) - m)
                    Y1 = min(H, int(yy1) + m)
                    return gray[Y0:Y1, X0:X1]
                ncc_g = match_char_ncc(crop_ch(a1), T["gu"], s)
                ncc_w = match_char_ncc(crop_ch(b1), T["wen"], s)
                if ncc_g < 0.62 or ncc_w < 0.68:
                    continue
            labels.append((c["cx"], a1[1], b1[2],
                           round(ncc_g, 3) if ncc_g is not None else None,
                           round(ncc_w, 3) if ncc_w is not None else None))
            # 标签后一个大字：同列下方；或 wrap 到左列顶（先查连通分量，碎片用墨块兜底）
            bb = None
            for X in big:
                if abs(X[0] - b1[0]) <= 0.80 * h0 and X[1] >= b1[2] and X[1] - b1[2] <= 1.15 * h0:
                    bb = [int(X[0] - X[3] / 2), int(X[1]), int(X[0] + X[3] / 2), int(X[2])]
                    break
            if bb is None:
                for X in big:
                    dx = X[0] - b1[0]
                    if -2.9 * h0 <= dx <= -0.4 * h0 and X[1] <= by0 + 1.50 * h0 and \
                            b1[2] >= by1 - 2.2 * h0:
                        bb = [int(X[0] - X[3] / 2), int(X[1]), int(X[0] + X[3] / 2), int(X[2])]
                        break
            if bb is None:
                mb = ink_mass_box(ink_res, b1[0] - 1.3 * h0, b1[0] + 1.3 * h0,
                                  b1[2] + 0.02 * h0, b1[2] + 2.7 * h0, h0, s)
                if mb is not None:
                    hh, ww = mb[3] - mb[1], mb[2] - mb[0]
                    if 1.15 * h0 <= hh <= 3.1 * h0 and 0.55 * h0 <= ww <= 3.1 * h0:
                        bb = [int(v) for v in mb]
            if bb is None:
                continue
            if not any(iou(bb, r) > 0.30 for r in res):
                res.append(bb)
            # 连续古文变体：紧接其后（同列下方）同尺寸大字也算古文变体
            cx = (bb[0] + bb[2]) / 2
            for _k in range(2):
                fu = fragment_union_box(ink_res, comps, cx - 1.0 * h0, cx + 1.0 * h0,
                                        bb[3] + 0.02 * h0, bb[3] + 2.6 * h0, h0, s)
                if fu is None:
                    break
                hh2, ww2 = fu[3] - fu[1], fu[2] - fu[0]
                if not (1.0 * h0 <= hh2 <= 3.1 * h0 and 0.5 * h0 <= ww2 <= 3.1 * h0):
                    break
                if (fu[1] - bb[3]) > 1.05 * h0:
                    break
                if any(iou(fu, r) > 0.30 for r in res):
                    break
                res.append([int(v) for v in fu])
                bb = fu
                cx = (bb[0] + bb[2]) / 2
    return res, labels


# ----------------------------------------------------------------------------
# 质量 / 合并
# ----------------------------------------------------------------------------
def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua else 0.0


def clamp(v, a=0.0, b=1.0):
    return max(a, min(b, v))


def glyph_quality(box, ink, h0, s):
    """候选框「像不像一个字头字形」：方形度 + 单主分量 + 尺寸带。"""
    x0, y0, x1, y1 = box
    H, W = ink.shape
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    w, h = x1 - x0, y1 - y0
    if w < 5 * s or h < 5 * s:
        return -1.0
    sr, wr = h / h0, w / h0
    ar = w / max(1, h)
    sub = ink[y0:y1, x0:x1]
    area = int(sub.sum())
    n, lab, st, _ = cv2.connectedComponentsWithStats(sub, 8)
    comps = [(int(st[i, 3]), int(st[i, 4])) for i in range(1, n) if st[i, 4] >= 25 * s * s]
    comps.sort(key=lambda t: -t[1])
    dom = comps[0][1] / max(1, area) if comps else 0.0
    bh = comps[0][0] / h if comps else 0.0
    # 扁平字头：按宽度
    if FLAT_SR[0] <= sr <= FLAT_SR[1] and FLAT_WR[0] <= wr <= FLAT_WR[1] and area >= 200 * s * s:
        return 0.80 + 0.15 * clamp((dom - 0.5) / 0.5) + 0.05 * clamp((0.05 - abs(sr - 0.3)) / 0.25)
    sq = math.exp(-(math.log(max(ar, 1e-3))) ** 2 / (2 * 0.30 ** 2))
    sz = 1.0 if HEAD_SR[0] <= sr <= HEAD_SR[1] else clamp(1 - abs(sr - 2.1) / 0.75)
    dom_s = clamp((dom - 0.25) / 0.5)
    bh_s = clamp((bh - 0.40) / 0.40)
    return 0.32 * sq + 0.28 * dom_s + 0.24 * bh_s + 0.16 * sz


def dedupe(props, ink, h0, s, iou_thr=0.42):
    """按字形质量优先去重（质量高者先保留）。props: [(box, src)]"""
    scored = []
    for b, src in props:
        q = glyph_quality(b, ink, h0, s)
        if q < 0:
            continue
        scored.append((q, b, src))
    scored.sort(key=lambda t: -t[0])
    keep = []
    for q, b, src in scored:
        if all(iou(b, k[1]) < iou_thr for k in keep):
            keep.append((q, b, src))
    return [(b, src, q) for q, b, src in keep]


# ----------------------------------------------------------------------------
# 候选提案
# ----------------------------------------------------------------------------
def refine_v3(ink, box, s=1.0):
    """种子 + 多数归属生长（v1.6 同款，按 dpi 缩放）。"""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    px, py = int(w * 0.3) + int(6 * s), int(h * 0.3) + int(6 * s)
    X0, Y0 = max(0, x0 - px), max(0, y0 - py)
    X1, Y1 = min(ink.shape[1], x1 + px), min(ink.shape[0], y1 + py)
    sub = ink[Y0:Y1, X0:X1]
    n, lab, stats, _ = cv2.connectedComponentsWithStats(sub, 8)
    ix0, iy0 = int((x0 - X0) + w * 0.25), int((y0 - Y0) + h * 0.25)
    ix1, iy1 = int((x0 - X0) + w * 0.75), int((y0 - Y0) + h * 0.75)
    seed = np.zeros_like(sub, dtype=bool)
    comps = {}
    for i in range(1, n):
        if stats[i, 4] < 25 * s * s:
            continue
        comp = (lab == i)
        comps[i] = comp
        if comp[iy0:iy1, ix0:ix1].any():
            seed |= comp
    if not seed.any():
        return None
    grown = seed.copy()
    ker = cv2.getStructuringElement(cv2.MORPH_RECT, (int(15 * s) | 1, int(15 * s) | 1))
    for _ in range(2):
        band = cv2.dilate(grown.astype(np.uint8), ker) > 0
        added = False
        for i, comp in comps.items():
            if (grown & comp).any():
                continue
            if (comp & band).sum() >= 0.4 * max(1, comp.sum()):
                grown |= comp
                added = True
        if not added:
            break
    ys, xs = np.where(grown)
    bx0, by0 = int(xs.min()), int(ys.min())
    bx1, by1 = int(xs.max()) + 1, int(ys.max()) + 1
    # 方形度驱动补并（亻/言旁与主体间隙可达 15-30px@150；并邻列会变长条）
    for _ in range(3):
        bw, bh = bx1 - bx0, by1 - by0
        if bw >= 0.7 * bh and bh >= 0.7 * bw:
            break
        band = cv2.dilate(grown.astype(np.uint8),
                          cv2.getStructuringElement(cv2.MORPH_RECT,
                                                    (int(45 * s) | 1, int(45 * s) | 1))) > 0
        best = None
        for i, comp in comps.items():
            if (grown & comp).any():
                continue
            npts = comp.sum()
            if npts < 200 * s * s:
                continue
            cys, cxs = np.where(comp)
            cx0, cx1 = int(cxs.min()), int(cxs.max()) + 1
            cy0, cy1 = int(cys.min()), int(cys.max()) + 1
            my0, my1 = min(by0, cy0), max(by1, cy1)
            mx0, mx1 = min(bx0, cx0), max(bx1, cx1)
            mw, mh = mx1 - mx0, my1 - my0
            if mw > 130 * s or mh > 130 * s:
                continue
            ar = mw / max(1, mh)
            if not (0.7 <= ar <= 1.4):
                continue
            if best is None or npts > best[0]:
                best = (npts, comp, (mx0, my0, mx1, my1))
        if best is None:
            break
        grown |= best[1]
        bx0, by0, bx1, by1 = best[2]
    return [int(X0 + bx0), int(Y0 + by0), int(X0 + bx1), int(Y0 + by1)]


def propose_v16(ink_res, h0, s):
    """P1：v1.6 提案（不丢弃，全部带出来给分类器）。"""
    thr = max(45 * s, 1.5 * h0)
    cores = cv2.erode(ink_res, cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                                         (int(5 * s) | 1, int(5 * s) | 1)))
    blobs = cv2.dilate(cores, cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                                        (int(18 * s) | 1, int(18 * s) | 1)))
    nb, _, sb, _ = cv2.connectedComponentsWithStats(blobs, connectivity=8)
    cands = []
    for i in range(1, nb):
        x, y, w, h, area = sb[i]
        if max(w, h) < thr or w >= 12 * h or h >= 12 * w:
            continue
        cands.append([int(x), int(y), int(x + w), int(y + h)])
    return cands


def largest_comp_box(ink_res, box, h0, s):
    """框内最大连通域 bbox（用于把粘连大框拆回单字形）。"""
    x0, y0, x1, y1 = box
    H, W = ink_res.shape
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    sub = ink_res[y0:y1, x0:x1]
    n, lab, st, _ = cv2.connectedComponentsWithStats(sub, 8)
    best = None
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a < 100 * s * s:
            continue
        # 优先「高度达字头带」的分量
        if h < 1.2 * h0:
            continue
        score = a
        if best is None or score > best[0]:
            best = (score, (int(x0 + x), int(y0 + y), int(x0 + x + w), int(y0 + y + h)))
    return best[1] if best else None


def propose_components(ink_res, comps, h0, s):
    """P3：原墨连通域直接提案（字头尺寸带 / 扁平 / 竖长窄 / 贴页缘）。"""
    H, W = ink_res.shape
    out = []
    for x, y, w, h, a in comps:
        sr, wr = h / h0, w / h0
        box = None
        if a >= 300 * s * s and 1.40 <= sr <= 2.85 and 0.30 <= wr <= 2.90:
            box = [x, y, x + w, y + h]
        elif a >= 180 * s * s and FLAT_SR[0] <= sr <= FLAT_SR[1] and FLAT_WR[0] <= wr <= FLAT_WR[1]:
            box = [x, y, x + w, y + h]
        elif a >= 300 * s * s and 1.40 <= sr <= 2.85 and 0.12 <= wr < 0.36:
            box = [x, y, x + w, y + h]
        if box is None:
            continue
        # 贴页缘的单独标记（可能是被裁的字头）
        src = "edge" if (x <= 6 * s or x + w >= W - 6 * s) else "raw"
        out.append((box, src))
    return out


# ----------------------------------------------------------------------------
# 特征
# ----------------------------------------------------------------------------
def ring_score(crop_ink, h0, s):
    """印刷圆圈检测：Hough 圆 + 圆周墨覆盖。返回 (score, radius/h0)。"""
    c = cv2.GaussianBlur((crop_ink * 255).astype(np.uint8), (5, 5), 1.2)
    rmin = max(8, int(0.72 * h0))
    rmax = max(rmin + 4, int(1.50 * h0))
    cir = cv2.HoughCircles(c, cv2.HOUGH_GRADIENT, dp=1.0, minDist=max(10, int(h0)),
                           param1=80, param2=24, minRadius=rmin, maxRadius=rmax)
    if cir is None:
        return 0.0, 0.0
    H, W = crop_ink.shape
    best, bestr = 0.0, 0.0
    for cx, cy, rad in cir[0][:4]:
        if not (0.80 * h0 <= rad <= 1.45 * h0):
            continue
        if not (rad * 0.6 < cx < W - rad * 0.6 and rad * 0.6 < cy < H - rad * 0.6):
            continue
        hits = 0
        nang = 48
        for k in range(nang):
            th = 2 * np.pi * k / nang
            for dr in (-2.0 * s, 0, 2.0 * s):
                xx = int(round(cx + (rad + dr) * np.cos(th)))
                yy = int(round(cy + (rad + dr) * np.sin(th)))
                if 0 <= yy < H and 0 <= xx < W and crop_ink[yy, xx]:
                    hits += 1
                    break
        cov = hits / nang
        sc = cov * min(1.0, rad / (1.02 * h0))
        if sc > best:
            best, bestr = sc, rad
    return float(best), (float(bestr / h0) if bestr else 0.0)


def box_features(ink_res, box, h0, s, ctx, side, do_ring=True):
    x0, y0, x1, y1 = box
    H, W = ink_res.shape
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    w, h = x1 - x0, y1 - y0
    if w < 4 or h < 4:
        return None
    sub = ink_res[y0:y1, x0:x1]
    area = int(sub.sum())
    if area < 40 * s * s:
        return None
    sr, wr = h / h0, w / h0
    ar = w / max(1, h)
    f = {
        "w": int(w), "h": int(h),
        "size_ratio": round(sr, 3),
        "w_ratio": round(wr, 3),
        "squareness": round(ar, 3),
        "ink_ratio": round(area / max(1, w * h), 3),
        "area": area,
    }
    n, lab, st, _ = cv2.connectedComponentsWithStats(sub, 8)
    comps = []
    for i in range(1, n):
        hh, aa, ww = int(st[i, 3]), int(st[i, 4]), int(st[i, 2])
        if aa >= 20 * s * s:
            comps.append((hh, aa, ww))
    comps.sort(key=lambda t: -t[1])
    f["n_comp"] = len(comps)
    if comps:
        f["dom_frac"] = round(comps[0][1] / max(1, area), 3)
        f["max_comp_h"] = comps[0][0]
        f["max_comp_h_ratio"] = round(comps[0][0] / h, 3)
        f["n_comp_ge32"] = sum(1 for hh, aa, ww in comps if hh >= 0.32 * h)
    else:
        f.update({"dom_frac": 0.0, "max_comp_h": 0, "max_comp_h_ratio": 0.0, "n_comp_ge32": 0})
    # 行带结构
    rowink = sub.sum(axis=1)
    thr = max(0, int(0.015 * w))
    ink_rows = rowink > thr
    band_h, cur, gaps = [], 0, []
    for v in ink_rows:
        if v:
            if cur > 0:
                gaps.append(cur)
            cur = 0
            band_h.append(0)
            # 简化：重新统计
        else:
            cur += 1
    # 重新算：墨带高度
    band_h = []
    cur = 0
    for v in ink_rows:
        if v:
            cur += 1
        else:
            if cur > 0:
                band_h.append(cur)
            cur = 0
    if cur > 0:
        band_h.append(cur)
    f["n_ink_bands"] = len(band_h)
    f["max_band_frac"] = round(max(band_h) / h, 3) if band_h else 0.0
    # 笔画粗细（DT 97 分位 ≈ 半笔宽）
    pad = int(6 * s)
    crop = ink_res[max(0, y0 - pad):min(H, y1 + pad), max(0, x0 - pad):min(W, x1 + pad)]
    dt = cv2.distanceTransform(crop.astype(np.uint8), cv2.DIST_L2, 5)
    vals = dt[crop > 0]
    stroke = float(np.percentile(vals, 97)) if len(vals) else 0.0
    f["stroke_ratio"] = round(stroke / h0, 3)
    # 圈字
    squareish = 0.6 <= ar <= 1.7 and 1.0 <= sr <= 2.6
    if do_ring and squareish:
        rs, rr = ring_score(crop, h0, s)
    else:
        rs, rr = 0.0, 0.0
    f["ring_score"] = round(rs, 3)
    f["ring_r"] = round(rr, 3)
    # 位置
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    f["cx"], f["cy"] = int(cx), int(cy)
    f["half"] = side
    tx0, tx1 = ctx["x_text"]
    band_y0, band_y1 = ctx["y0"], ctx["y1"]
    near_outer = (cx < 3.6 * h0) if side == "L" else (cx > W - 3.6 * h0)
    f["outer_edge"] = bool(near_outer)
    # 版心条：书眉小字条（真实边界由 strip_borders 给出，前后留 1.2h0 宽容）
    sx = ctx.get("strip_x")
    if sx is not None:
        if side == "L":
            f["margin_strip"] = bool(cx < sx + 1.2 * h0)
        else:
            f["margin_strip"] = bool(cx > sx - 1.2 * h0)
    else:
        f["margin_strip"] = bool(near_outer)
    f["outside_band"] = bool(cy < band_y0 - 0.6 * h0 or cy > band_y1 + 0.6 * h0)
    f["edge_flag"] = bool(x0 <= 3 or y0 <= 3 or x1 >= W - 3 or y1 >= H - 3)
    # 邻域墨密度（字头嵌在注文里；书眉孤立）
    s_ = max(w, h)
    nx0, ny0 = max(0, int(cx - 1.5 * s_)), max(0, int(cy - 1.5 * s_))
    nx1, ny1 = min(W, int(cx + 1.5 * s_)), min(H, int(cy + 1.5 * s_))
    ringmask = np.ones((ny1 - ny0, nx1 - nx0), bool)
    ringmask[y0 - ny0:y1 - ny0, x0 - nx0:x1 - nx0] = False
    outer = ink_res[ny0:ny1, nx0:nx1][ringmask]
    f["context_ink"] = round(float(outer.mean()), 3) if outer.size else 0.0
    f["col_top"] = col_top(ink_res, box, h0, s, ctx)
    # 边框/内嵌小字：印刷方框围住的注文（音注来源、字通/籍詩 类）
    col_frac = sub.sum(axis=0) / max(1, h)
    row_frac = sub.sum(axis=1) / max(1, w)
    f["border_frame"] = bool(col_frac.max() >= 0.80 and row_frac.max() >= 0.80)

    def _runs(row):
        rr, cur = [], 0
        for v in row:
            if v:
                cur += 1
            elif cur:
                rr.append(cur)
                cur = 0
        if cur:
            rr.append(cur)
        return rr
    thin = []
    for fy in (0.30, 0.50, 0.70):
        rr = _runs(sub[min(h - 1, max(0, int(h * fy)))])
        if rr:
            thin.append(min(rr[0], rr[-1]))
    f["edge_thin"] = round(min(thin) / h0, 3) if thin else 9.0
    bd = max(2, int(0.02 * max(1, min(w, h))))
    cover = (sub[0:bd].any(axis=0).mean() + sub[-bd:].any(axis=0).mean() +
             sub[:, 0:bd].any(axis=1).mean() + sub[:, -bd:].any(axis=1).mean()) / 4.0
    f["frame_cover"] = round(float(cover), 3)
    ix, iy = int(w * 0.13), int(h * 0.13)
    if w > 2 * ix + 6 and h > 2 * iy + 6:
        inner = sub[iy:h - iy, ix:w - ix]
        nin, _, sti, _ = cv2.connectedComponentsWithStats(inner, 8)
        cnt = 0
        for j in range(1, nin):
            hh, aa = int(sti[j, 3]), int(sti[j, 4])
            if 0.66 * h0 <= hh <= 1.38 * h0 and aa >= 0.03 * w * h:
                cnt += 1
        f["n_inner_char"] = cnt
    else:
        f["n_inner_char"] = 0
    return f


def col_top(ink_res, box, h0, s, ctx):
    """候选上方同列 1.3h0 内是否无墨（= 位于列首）。扁笔字头（一）用。"""
    x0, y0, x1, y1 = box
    H, W = ink_res.shape
    cx = (x0 + x1) / 2
    X0 = max(0, int(cx - 0.90 * h0))
    X1 = min(W, int(cx + 0.90 * h0))
    Y0 = max(int(ctx["y0"]) + int(0.85 * h0), int(y0 - 1.30 * h0))
    Y1 = max(Y0 + 1, int(y0 - 2))
    if Y1 <= Y0 or X1 <= X0:
        return True
    above = int(ink_res[Y0:Y1, X0:X1].sum())
    return above < max(20, int(18 * s * s))


# ----------------------------------------------------------------------------
# 结构检测：古文标签三元组 / 标题块 / TOC
# ----------------------------------------------------------------------------
def detect_title_zones(gray, dpi, ink_res, h0, s, ctx, side):
    """标题块：模板匹配康/典；返回 title zone bbox 列表（工作分辨率坐标）。"""
    zones = find_title_block(gray, dpi, h0 / s)
    if not zones:
        return []
    scale = s
    return [[int(v * scale) for v in z] for z in zones]


def classify(f, h0, s, ctx, guwen_flag=False, title_flag=False):
    """规则打分。Lead 裁决（2026-11-08）：宁多勿少——不确定时给 headword 中等分，
    glue/ring/margin/title 只在「强结构证据」下压过 headword。"""
    sc = {k: 0.0 for k in ("headword", "guwen", "title", "ring", "glue", "margin")}
    sr, wr, ar = f["size_ratio"], f["w_ratio"], f["squareness"]
    dom = f["max_comp_h_ratio"]
    by0, by1 = ctx["y0"], ctx["y1"]
    band = HEAD_SR[0] <= sr <= HEAD_SR[1]
    square = 0.62 <= ar <= 1.58
    flat = (FLAT_SR[0] <= sr <= FLAT_SR[1] and FLAT_WR[0] <= wr <= FLAT_WR[1]
            and f["ink_ratio"] >= 0.08)
    tall_thin = (1.45 <= sr <= 2.90 and 0.16 <= wr <= 0.68)
    narrow_tall = (0.50 <= ar < 0.62 and 1.70 <= sr <= 2.60 and dom >= 0.55)
    glyph_like = (square and 1.38 <= sr <= 3.05) or flat or tall_thin or narrow_tall
    # ---------------- 强结构证据（否决项） ----------------
    strong_margin = False
    if f["outside_band"]:
        strong_margin = True
    if f["cy"] < by0 + 0.28 * h0 or f["cy"] > by1 - 0.28 * h0:
        strong_margin = True
    if f["edge_flag"] and not glyph_like:
        strong_margin = True
    if f["margin_strip"] and (not glyph_like or ar < 0.80 or wr < 1.15 or sr > 2.70):
        strong_margin = True
    if max(f["w"], f["h"]) > 3.6 * max(1, min(f["w"], f["h"])) and not flat:
        strong_margin = True
    if f["w"] > 6.5 * h0 or f["h"] > 6.5 * h0:
        strong_margin = True
    if f["context_ink"] < 0.012:
        strong_margin = True
    # 扁平笔贴上下框（版框线残段）
    if flat and (f["cy"] < by0 + 1.20 * h0 or f["cy"] > by1 - 1.20 * h0):
        strong_margin = True
    strong_ring = (f["ring_score"] >= 0.62 and f["ring_r"] >= 0.82)
    strong_title = bool(title_flag)
    if ctx.get("is_toc") and glyph_like:
        strong_title = True
    # 强 glue：竖向双字（h≈2.2-3.0h0、宽≈1h0、两条墨带）或横向双字（宽≈2.4-3.4h0）
    vert_pair = (2.15 <= sr <= 3.05 and wr <= 1.42 and f["n_ink_bands"] >= 2
                 and 0.28 <= f["max_band_frac"] <= 0.62)
    horiz_pair = (wr >= 2.25 and sr <= 1.35 and f["n_comp_ge32"] >= 2
                  and dom < 0.62)
    frag_mess = (dom < 0.28 and f["n_comp_ge32"] >= 6 and sr <= 3.05
                 and f.get("ink_ratio", 0.3) < 0.18)
    strong_glue = vert_pair or horiz_pair or frag_mess
    # ---------------- 打分 ----------------
    if strong_margin:
        sc["margin"] = 0.95
        if glyph_like and f["context_ink"] >= 0.012:
            sc["headword"] = 0.25
    if strong_ring:
        sc["ring"] = 0.98
        sc["headword"] = 0.10
    if strong_title:
        sc["title"] = 0.97
        sc["headword"] = 0.0
    if guwen_flag and not strong_ring and not strong_margin:
        sc["guwen"] = 0.95
        sc["headword"] = 0.10
    # headword 基线（glyph 像字头就给中等以上分）
    if glyph_like and not guwen_flag and not strong_margin and not strong_title and not strong_ring:
        hw = 0.50
        if band and 0.68 <= ar <= 1.48:
            hw = 0.60
        if band and 0.72 <= ar <= 1.45 and dom >= 0.60:
            hw = 0.80
        # v3：版刻磨损导致的分量碎片（dom 低但单墨带、墨量正常）也按字头计
        if (band and 0.72 <= ar <= 1.45 and dom < 0.60 and f["n_ink_bands"] <= 2
                and f.get("max_band_frac", 0.0) >= 0.72
                and f.get("ink_ratio", 0.0) >= 0.12
                and f.get("n_inner_char", 0) < 2):
            hw = max(hw, 0.82)
        if band and 0.75 <= ar <= 1.40 and dom >= 0.80:
            hw = 0.90
        if dom >= 0.90 and 1.80 <= sr <= 2.45 and 0.80 <= ar <= 1.35:
            hw = 0.95
        if f["stroke_ratio"] >= 0.10:
            hw = min(0.97, hw + 0.02)
        if flat and (f.get("_chain") or f.get("col_top")):
            hw = max(hw, 0.88)
        if flat and not (f.get("_chain") or f.get("col_top")):
            hw = min(hw, 0.40)
        if tall_thin and not flat:
            hw = max(hw, 0.55)
        if narrow_tall:
            hw = max(hw, 0.52)
        if strong_glue:
            big_single_band = (1.70 <= sr <= 2.60 and 0.66 <= ar <= 1.48
                               and f["n_ink_bands"] <= 2
                               and f.get("max_band_frac", 0.0) >= 0.72
                               and f.get("ink_ratio", 0.0) >= 0.12
                               and f.get("n_inner_char", 0) < 2)
            if big_single_band:
                # v3：版刻磨损的大字形碎片（人部密排页实测漏检）优先保留 headword 中等分
                hw = max(hw, 0.68)
                sc["glue"] = min(sc["glue"], 0.60)
            else:
                hw = min(hw, 0.42)      # 拿不准：保留中等分
                sc["glue"] = 0.72
        sc["headword"] = max(sc["headword"], hw)
    elif not strong_margin:
        if strong_glue:
            sc["glue"] = 0.85
        elif sr > 2.9 or ar < 0.45 or ar > 2.6:
            sc["glue"] = 0.60
        else:
            sc["glue"] = 0.45
    # 圈字弱证据：给 ring 0.5 + headword 0.45（拿不准不判死）
    if 0.45 <= f["ring_score"] < 0.62 and glyph_like and not strong_ring:
        sc["ring"] = max(sc["ring"], 0.50)
        sc["headword"] = max(sc["headword"], 0.45)
    # 方框围住的注文/音注框 → 强 glue（强结构证据：边框覆盖/细边框贯穿 + 框内小字）
    fcov = f.get("frame_cover", 0.0)
    enclosure = False
    if f.get("n_inner_char", 0) >= 1 and f["dom_frac"] < 0.75:
        if fcov >= 0.40:
            enclosure = True
        elif (f.get("border_frame") and f.get("edge_thin", 9.0) <= 0.12
              and f["dom_frac"] < 0.45 and sr >= 2.15
              and (fcov >= 0.25 or f["n_comp"] >= 8)):
            enclosure = True
    if enclosure and not strong_title:
        sc["glue"] = max(sc["glue"], 0.85)
        sc["headword"] = min(sc["headword"], 0.40)
    if max(sc.values()) < 0.30:
        sc["glue"] = 0.35
    for k in sc:
        sc[k] = round(float(clamp(sc[k])), 3)
    return sc


def reading_order(cands, colpitch):
    """半版内阅读序：列右→左，列内上→下。同时写 col（0=最右列）/col_cx。"""
    if not cands:
        return cands
    items = sorted(cands, key=lambda c: -(c["box"][0] + c["box"][2]) / 2)
    cols = []
    for it in items:
        cx = (it["box"][0] + it["box"][2]) / 2
        if cols and cols[-1]["cx"] - cx <= 0.55 * colpitch:
            cols[-1]["items"].append(it)
            n = len(cols[-1]["items"])
            cols[-1]["cx"] += (cx - cols[-1]["cx"]) / n
        else:
            cols.append({"cx": cx, "items": [it]})
    out = []
    for ci, c in enumerate(cols):
        col_items = sorted(c["items"], key=lambda c2: c2["box"][1])
        for it in col_items:
            it["col"] = ci
            it["col_cx"] = int(c["cx"])
        out += col_items
    return out


# ----------------------------------------------------------------------------
# 分类（类分数）
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# 单页
# ----------------------------------------------------------------------------
def split_axis(ink_res, box, h0, axis):
    """沿 axis 把「多字粘连大框」切成单字框（切在低墨隙，块高 0.85-2.85h0）。"""
    x0, y0, x1, y1 = box
    sub = ink_res[y0:y1, x0:x1]
    if axis == "v":
        prof = sub.sum(axis=1)
        L = sub.shape[0]
        perp = sub.shape[1]
    else:
        prof = sub.sum(axis=0)
        L = sub.shape[1]
        perp = sub.shape[0]
    lim = 2.85 * h0
    if L <= lim:
        return [box]
    thr = max(1, int(0.012 * perp))
    cuts, run = [], 0
    for i, v in enumerate(prof):
        if v <= thr:
            run += 1
        else:
            if run >= max(2, int(2 * h0 * 0.06)):
                cuts.append(i - run // 2)
            run = 0
    if run >= max(2, int(2 * h0 * 0.06)):
        cuts.append(L - run // 2)
    bounds = [0] + [c for c in cuts if 0 < c < L] + [L]
    chunks, start = [], 0
    for i in range(1, len(bounds)):
        end = bounds[i]
        if end - start > lim and i > 1:
            prev = bounds[i - 1]
            if prev - start >= 0.85 * h0:
                chunks.append((start, prev))
                start = prev
    if L - start >= 0.85 * h0:
        chunks.append((start, L))
    out = []
    for a, b in chunks:
        if b - a < 0.85 * h0 or b - a > lim:
            continue
        if axis == "v":
            out.append([x0, y0 + int(a), x1, y0 + int(b)])
        else:
            out.append([x0 + int(a), y0, x0 + int(b), y1])
    return out if out else [box]


def split_props(props, ink_res, h0, s):
    """把细长/超高大框按需拆分（治 音部/韋部 大字标题粘连、注文竖排粘连）。"""
    out = []
    for b, src in props:
        w, h = b[2] - b[0], b[3] - b[1]
        parts = None
        if 2.35 * h0 < h <= 7.0 * h0 and 0.9 * h0 <= w <= 3.2 * h0 and h > 1.30 * w:
            parts = split_axis(ink_res, b, h0, "v")
        elif 2.35 * h0 < w <= 7.0 * h0 and 0.9 * h0 <= h <= 3.2 * h0 and w > 1.30 * h:
            parts = split_axis(ink_res, b, h0, "h")
        if parts is None or len(parts) <= 1:
            out.append((b, src))
        else:
            for p in parts:
                out.append((p, src + "_split"))
    return out


def subglyph_props(ink_res, box, h0, s):
    """v16 大框内部：把所有「字头尺寸带」的原墨分量都作为候选（拆回单字形）。"""
    x0, y0, x1, y1 = box
    H, W = ink_res.shape
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    sub = ink_res[y0:y1, x0:x1]
    n, lab, st, _ = cv2.connectedComponentsWithStats(sub, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a < 200 * s * s:
            continue
        sr, wr, ar = h / h0, w / h0, w / max(1, h)
        if 1.30 <= sr <= 2.95 and 0.40 <= wr <= 2.95 and 0.45 <= ar <= 2.0:
            out.append([int(x0 + x), int(y0 + y), int(x0 + x + w), int(y0 + y + h)])
        elif FLAT_SR[0] * h0 <= h <= FLAT_SR[1] * h0 and FLAT_WR[0] * h0 <= w <= FLAT_WR[1] * h0 and a >= 180 * s * s:
            out.append([int(x0 + x), int(y0 + y), int(x0 + x + w), int(y0 + y + h)])
    return out


def dilate_props(ink_res, comps, h0, s, band_y0, band_y1):
    """碎片修复提案：先小核膨胀再取连通域（治刻版磨损/断笔导致字头碎片化）。"""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(9 * s) | 1, int(9 * s) | 1))
    dil = cv2.dilate(ink_res, k)
    n, _, st, _ = cv2.connectedComponentsWithStats(dil, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        sr, wr, ar = h / h0, w / h0, w / max(1, h)
        if not (1.30 <= sr <= 3.05 and 0.40 <= wr <= 3.05 and 0.40 <= ar <= 2.2):
            continue
        x, y, w, h = int(x), int(y), int(w), int(h)
        if band_y0 - 0.6 * h0 <= y + h / 2 <= band_y1 + 0.6 * h0:
            out.append([x, y, x + w, y + h])
    return out


def to_150(gray, dpi):
    """把任意 dpi 灰度页降到 150dpi 当量（检测在 150 尺度做，坐标天然 150 当量）。"""
    s = dpi / 150.0
    if abs(s - 1.0) < 1e-6:
        return gray, 1.0
    h = int(round(gray.shape[0] / s))
    w = int(round(gray.shape[1] / s))
    return cv2.resize(gray, (w, h), interpolation=cv2.INTER_AREA), s


def detect_page_gray(gray, page_name, dpi, debug=False):
    """按半版输出候选。内部统一在 150dpi 当量尺度检测（坐标即 Lead 要求的 150dpi 当量）。"""
    gray, _scale = to_150(gray, dpi)
    H, W = gray.shape
    s = 1.0
    work_dpi = 150
    t0 = time.time()
    split = W // 2
    raw_ink = (gray <= BIN_T).astype(np.uint8)
    ink_res = page_ink(raw_ink, s)
    comps = components(ink_res, amin=max(20, int(20 * s * s)))
    h0 = estimate_h0(comps, s)
    band_y0, band_y1 = hline_band(raw_ink, s)
    maxrun, _bh = col_maxrun(raw_ink, band_y0, band_y1)
    xL_strip, xR_strip = strip_borders(raw_ink, band_y0, band_y1, s, W, split, maxrun)
    try:
        title_zones_150 = find_title_block(gray, work_dpi, h0 / s)
    except Exception:
        title_zones_150 = []
    tz = [[int(v * s) for v in z] for z in title_zones_150]
    halves = {}
    for side in ("R", "L"):
        xs0, xs1 = (0, split) if side == "L" else (split, W)
        vn, vn_full, vgroups = vline_count(raw_ink, band_y0, band_y1, xs0, xs1, s, maxrun)
        strip_x = xL_strip if side == "L" else xR_strip
        # 正文 x 范围（保守）：版心内边界 ~ 分页线
        if side == "L":
            x_text = [xL_strip, split]
        else:
            x_text = [split, xR_strip]
        # 透印/空白：正文带内区墨占比（去掉页缘与版心条）
        bx0 = max(xs0 + int(2 * h0), xL_strip + int(1.5 * h0)) if side == "L" else split
        bx1 = min(xs1 - int(2 * h0), xR_strip - int(1.5 * h0)) if side == "R" else split
        body = ink_res[band_y0 + int(10 * s):band_y1 - int(10 * s), bx0:max(bx0 + 5, bx1)]
        inner_frac = float(body.mean()) if body.size else 0.0
        blank = inner_frac < 0.075
        # TOC/总目页：大量「通高竖线」（栏线）+ 稀疏正文（13_0012 实测 nvf=9/inner=0.038）
        is_toc = bool(vn_full >= 7 and inner_frac < 0.12 and not blank)
        ctx = {"y0": band_y0, "y1": band_y1, "split": split,
               "x_text": [int(v) for v in x_text],
               "colpitch": 1.27 * h0, "strip_x": int(strip_x),
               "is_toc": bool(is_toc), "n_vlines": int(vn)}
        cands = []
        if not blank:
            # 古文三元组（模板校验）——也作为候选来源：古文变体是 gold 框的一种
            try:
                gboxes, glabels = find_guwen_labels(gray, ink_res, comps, h0, s, ctx, side)
            except Exception:
                gboxes, glabels = [], []
            props = []
            for b in propose_v16(ink_res, h0, s):
                cx = (b[0] + b[2]) / 2
                if not (xs0 - 5 <= cx <= xs1 + 5):
                    continue
                props.append((b, "v16"))
                gb = largest_comp_box(ink_res, b, h0, s)
                if gb is not None:
                    props.append((gb, "glyph"))
                for sb in subglyph_props(ink_res, b, h0, s):
                    props.append((sb, "subglyph"))
            chains, consumed = propose_chains(comps, h0, s, band_y0, band_y1)
            comps2 = [c for i, c in enumerate(comps) if i not in consumed]
            props += propose_components(ink_res, comps2, h0, s)
            for b in chains:
                props.append((b, "chain"))
            for b in dilate_props(ink_res, comps, h0, s, band_y0, band_y1):
                props.append((b, "dil"))
            for b in gboxes:
                props.append((b, "guwen"))
            props = [(b, src) for b, src in props
                     if xs0 - 5 <= (b[0] + b[2]) / 2 <= xs1 + 5]
            props = split_props(props, ink_res, h0, s)
            deduped = dedupe(props, ink_res, h0, s)
            # 被大字头框包住的扁笔（上/三 的横笔）不单独算候选
            keep2 = []
            for b, src, q in deduped:
                w, h = b[2] - b[0], b[3] - b[1]
                is_flat = (FLAT_SR[0] <= h / h0 <= FLAT_SR[1]
                           and FLAT_WR[0] <= w / h0 <= FLAT_WR[1])
                contained = False
                if is_flat:
                    A = w * h
                    for b2, src2, q2 in deduped:
                        if b2 is b:
                            continue
                        w2, h2 = b2[2] - b2[0], b2[3] - b2[1]
                        if h2 < 1.2 * h0:
                            continue
                        ix = max(0, min(b[2], b2[2]) - max(b[0], b2[0]))
                        iy = max(0, min(b[3], b2[3]) - max(b[1], b2[1]))
                        if ix * iy >= 0.80 * A:
                            contained = True
                            break
                if contained:
                    continue
                f0 = box_features(ink_res, b, h0, s, ctx, side) if False else None
                keep2.append((b, src, q))
            deduped = keep2
            for b, src, q in deduped:
                if b[2] - b[0] > 0.45 * W or b[3] - b[1] > 0.85 * H:
                    continue
                if b[2] - b[0] < 5 * s or b[3] - b[1] < 5 * s:
                    continue
                f = box_features(ink_res, b, h0, s, ctx, side)
                if f is None:
                    continue
                f["_q"] = round(q, 3)
                if src == "chain":
                    f["_chain"] = True
                cands.append({"box": [int(v) for v in b], "w": f["w"], "h": f["h"],
                              "src": src, "feat": f,
                              "size_ratio": f["size_ratio"],
                              "squareness": f["squareness"],
                              "ink_ratio": f["ink_ratio"],
                              "edge_flag": f["edge_flag"]})
            for c in cands:
                if any(iou(c["box"], gb) > 0.42 for gb in gboxes):
                    c["feat"]["_guwen"] = True
            # 标题块
            tset = set()
            if tz:
                for i, c in enumerate(cands):
                    cx = (c["box"][0] + c["box"][2]) / 2
                    cy = (c["box"][1] + c["box"][3]) / 2
                    for z in tz:
                        if z[0] <= cx <= z[2] and z[1] <= cy <= z[3]:
                            tset.add(i)
                            break
            for i, c in enumerate(cands):
                if i in tset:
                    c["feat"]["_title"] = True
            for c in cands:
                c["cls"] = classify(c["feat"], h0, s, ctx,
                                    guwen_flag=c["feat"].get("_guwen", False),
                                    title_flag=c["feat"].get("_title", False))
            cands = reading_order(cands, ctx["colpitch"])
            # 给候选补编号（阅读序），raw 坐标保留
        # 坐标统一为 150dpi 当量页坐标（Lead 2026-11-08 裁决）
        if abs(s - 1.0) > 1e-6:
            for c in cands:
                b = c["box"]
                c["box"] = [int(round(v / s)) for v in b]
                c["w"] = int(round(c["w"] / s))
                c["h"] = int(round(c["h"] / s))
        for i, c in enumerate(cands):
            c["idx"] = i + 1
        counts = {}
        for c in cands:
            k = max(c["cls"], key=lambda kk: c["cls"][kk])
            counts[k] = counts.get(k, 0) + 1
            c["argmax"] = k
        # 严格计数（用于半版字头数金标对账）：argmax=headword 且 headword 分 >= 0.80
        strict = sum(1 for c in cands
                     if c["argmax"] == "headword" and c["cls"]["headword"] >= 0.80)
        halves[side] = {
            "blank": bool(blank),
            "inner_frac": round(inner_frac, 4),
            "toc_like": bool(is_toc),
            "n_vlines": int(vn),
            "n_vlines_full": int(vn_full),
            "strip_x": int(strip_x),
            "y_range": [int(band_y0), int(band_y1)],
            "x_text": ctx["x_text"],
            "n": len(cands),
            "count_by_cls": counts,
            "count_headword": strict,
            "count_headword_soft": counts.get("headword", 0),
            "cands": cands,
        }
    ms = round((time.time() - t0) * 1000, 1)
    res = {"page": page_name, "dpi": dpi, "h0_prior": H0_PRIOR, "halves": halves,
           "stats": {"page": page_name, "dpi": dpi, "W": int(W), "H": int(H),
                     "h0": round(h0 / s, 2), "split_x": int(split), "ms": ms}}
    if debug:
        res["debug"] = {"title_zones": tz, "labels": {
            side: halves[side].get("labels", []) for side in ("L", "R")}}
    return res


def render_page(pdf_id, page_no, dpi, page_dir=None):
    """取页灰度图：优先 page_dir 缓存（仅 150dpi 有），否则 fitz 直渲染。"""
    stem = f"{pdf_id}_{page_no:04d}"
    if page_dir:
        p = os.path.join(page_dir, stem + ".png")
        if os.path.exists(p):
            g = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
            if g is not None:
                return g
    import fitz
    import warnings
    warnings.filterwarnings("ignore")
    pdf_path = os.path.join(ROOT, "康熙字典", pdf_map()[pdf_id])
    doc = _DOCS.get(pdf_path)
    if doc is None:
        doc = fitz.open(pdf_path)
        _DOCS[pdf_path] = doc
    try:
        pg = doc[page_no - 1]           # 实测：扫描页号 = PDF index+1
        pix = pg.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        g = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        return np.ascontiguousarray(g)
    finally:
        pass


_PDF_MAP = None
_DOCS = {}


def pdf_map():
    global _PDF_MAP
    if _PDF_MAP is None:
        p = os.path.join(ROOT, "work", "t2", "pdf_map.json")
        if os.path.exists(p):
            _PDF_MAP = json.load(open(p))
        else:
            _PDF_MAP = {f"{i:02d}": f for i in range(14)}
    return _PDF_MAP


# ----------------------------------------------------------------------------
# montage
# ----------------------------------------------------------------------------
CLS_COLOR = {  # BGR
    "headword": (0, 170, 0),
    "guwen": (200, 60, 200),
    "title": (0, 140, 255),
    "ring": (0, 0, 230),
    "glue": (230, 120, 0),
    "margin": (150, 150, 150),
}


def make_montage(page_result, gray, out_path, scale=1.0, min_score=0.45):
    """评审拼图（参考 work/lead/mont 裁框拼图格式）。

    输出：
      <stem>_cands[_k].png  候选裁框拼图（每行 8 格、按阅读序 R→L、标签 R3/L2 + 类别色）
      <stem>_page.png       整页编号框叠加图（查漏检用）
    只列「可能是字头/古文/标题/圈」的候选（hw>=0.40 或 argmax ∈ guwen/title/ring）。
    """
    from PIL import Image, ImageDraw, ImageFont
    try:
        from reffont import path as _ref_font_path, index as _ref_font_index
        f_big = ImageFont.truetype(_ref_font_path(), 20, index=_ref_font_index())
        f_sm = ImageFont.truetype(_ref_font_path(), 15, index=_ref_font_index())
    except Exception:
        f_big = f_sm = None
    H, W = gray.shape
    base = out_path[:-4] if out_path.endswith(".png") else out_path
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    st = page_result["stats"]
    hl, hr = page_result["halves"]["L"], page_result["halves"]["R"]
    # 评审候选过滤
    cells = []
    for side in ("R", "L"):
        for c in page_result["halves"][side]["cands"]:
            am = c.get("argmax") or max(c["cls"], key=lambda k: c["cls"][k])
            hw = c["cls"]["headword"]
            if am in ("guwen", "title", "ring") or hw >= 0.40:
                cells.append((side, c, am))
    COLS, CW, CH = 8, 236, 250
    parts = []
    for si in range(0, max(1, (len(cells) + 23) // 24)):
        chunk = cells[si * 24:(si + 1) * 24]
        if not chunk:
            break
        rows = (len(chunk) + COLS - 1) // COLS
        sheet = Image.new("RGB", (COLS * CW + 8, rows * CH + 46), (245, 245, 245))
        dr = ImageDraw.Draw(sheet)
        t1 = (f"{page_result['page']}  h0={st['h0']}@150  "
              f"L: head={hl['count_headword']} n={hl['n']} blank={hl['blank']}  |  "
              f"R: head={hr['count_headword']} n={hr['n']} blank={hr['blank']}  "
              f"[列全部评审候选 {len(cells)}，第 {si + 1} 页]")
        dr.text((6, 4), t1, fill=(0, 0, 0), font=f_big)
        dr.text((6, 26), "绿=head 紫=古文 橙=标题 红=圈 蓝=粘连 灰=书眉（方框色=类别）",
                fill=(70, 70, 70), font=f_sm)
        for i, (side, c, am) in enumerate(chunk):
            r, cc = divmod(i, COLS)
            cx0, cy0 = 4 + cc * CW, 40 + r * CH
            x0, y0, x1, y1 = c["box"]
            w, h = x1 - x0, y1 - y0
            m = int(max(w, h) * 0.55) + 8
            X0, Y0 = max(0, x0 - m), max(0, y0 - m)
            X1, Y1 = min(W, x1 + m), min(H, y1 + m)
            crop = gray[Y0:Y1, X0:X1]
            avail_w, avail_h = CW - 14, CH - 46
            sc_f = min(avail_w / max(1, crop.shape[1]), avail_h / max(1, crop.shape[0]))
            nw, nh = max(8, int(crop.shape[1] * sc_f)), max(8, int(crop.shape[0] * sc_f))
            crop = cv2.resize(crop, (nw, nh), interpolation=cv2.INTER_CUBIC)
            crop_bgr = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
            col = CLS_COLOR.get(am, (128, 128, 128))
            bx, by = int((x0 - X0) * sc_f), int((y0 - Y0) * sc_f)
            cv2.rectangle(crop_bgr, (bx, by), (int(bx + w * sc_f), int(by + h * sc_f)), col, 2)
            ox, oy = cx0 + 7, cy0 + 26 + (avail_h - nh) // 2
            sheet.paste(Image.fromarray(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)), (ox, oy))
            hwv = c["cls"]["headword"]
            tag = f"{side}{c['idx']} {am}"
            dr.text((cx0 + 5, cy0 + 1), tag, fill=col[::-1], font=f_big)
            dr.text((cx0 + 5, cy0 + 19),
                    f"hw{hwv:.2f} {c['w']}x{c['h']} sr{c['size_ratio']:.2f}",
                    fill=(80, 80, 80), font=f_sm)
        p1 = base + (f"_cands_{si + 1}.png" if si or len(cells) > 24 else "_cands.png")
        sheet.save(p1)
        parts.append(p1)
    # 整页叠加图
    vis = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for side in ("R", "L"):
        for c in page_result["halves"][side]["cands"]:
            b = c["box"]
            am = c.get("argmax") or max(c["cls"], key=lambda k: c["cls"][k])
            col = CLS_COLOR.get(am, (128, 128, 128))
            thick = 2 if am in ("headword", "guwen", "ring", "title") else 1
            cv2.rectangle(vis, (b[0], b[1]), (b[2], b[3]), col, thick)
            cv2.putText(vis, f"{side}{c['idx']}", (b[0] + 1, max(13, b[1] - 3)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1)
    cv2.line(vis, (W // 2, 0), (W // 2, H), (0, 0, 255), 1)
    header = np.full((64, W, 3), 245, np.uint8)
    simg = Image.fromarray(np.vstack([header, vis]))
    dr = ImageDraw.Draw(simg)
    t1 = (f"{page_result['page']}  h0={st['h0']}@150  "
          f"L: head={hl['count_headword']} n={hl['n']} blank={hl['blank']} toc={hl['toc_like']}  |  "
          f"R: head={hr['count_headword']} n={hr['n']} blank={hr['blank']} toc={hr['toc_like']}")
    t2 = ("L " + str(hl["count_by_cls"]) + "   R " + str(hr["count_by_cls"]) +
          "   [绿=head 紫=古文 橙=标题 红=圈 蓝=粘连 灰=书眉]")
    dr.text((6, 4), t1, fill=(0, 0, 0), font=f_big)
    dr.text((6, 30), t2, fill=(60, 60, 60), font=f_sm)
    if scale != 1.0:
        simg = simg.resize((int(simg.width * scale), int(simg.height * scale)), Image.LANCZOS)
    p2 = base + "_page.png"
    simg.save(p2)
    parts.append(p2)
    return parts


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def parse_pages(spec):
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def _job(args_tuple):
    cv2.setNumThreads(1)
    pdf_id, page, dpi, out_dir, page_dir, montage_dir, montage_scale, render_dpi = args_tuple
    stem = f"{pdf_id}_{page:04d}"
    rd = render_dpi or (150 if dpi > 150 else dpi)
    gray = render_page(pdf_id, page, rd, page_dir)
    gray150, _ = to_150(gray, rd)
    res = detect_page_gray(gray150, stem, 150)
    res["dpi"] = dpi
    res["stats"]["render_dpi"] = rd
    res["stats"]["coord_dpi"] = 150
    with open(os.path.join(out_dir, stem + ".json"), "w") as fh:
        json.dump(res, fh, ensure_ascii=False)
    if montage_dir:
        make_montage(res, gray150, os.path.join(montage_dir, stem + ".png"), montage_scale)
    return stem, res["stats"]["ms"], (gray150.shape[1], gray150.shape[0])


def run_pages(pdf_id, pages, dpi, out_dir, page_dir=None, montage_dir=None,
              montage_scale=1.0, workers=8, render_dpi=None):
    os.makedirs(out_dir, exist_ok=True)
    if montage_dir:
        os.makedirs(montage_dir, exist_ok=True)
    t0 = time.time()
    tasks = [(pdf_id, p, dpi, out_dir, page_dir, montage_dir, montage_scale, render_dpi) for p in pages]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_job, t) for t in tasks]
            for fut in as_completed(futs):
                stem, ms, shape = fut.result()
                print(f"{stem} {shape[0]}x{shape[1]} {ms}ms", flush=True)
    else:
        for t in tasks:
            stem, ms, shape = _job(t)
            print(f"{stem} {shape[0]}x{shape[1]} {ms}ms", flush=True)
    dt = time.time() - t0
    print(f"done {len(pages)} pages in {dt:.1f}s ({dt / max(1, len(pages)):.2f}s/page wall)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default="01")
    ap.add_argument("--pages", default="6-40")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--out", default=os.path.join(ROOT, "work", "detect2", "boxes"))
    ap.add_argument("--page-dir", default=None, help="150dpi 缓存页目录（work/t00/pages）")
    ap.add_argument("--montage", default=None, help="montage 输出目录")
    ap.add_argument("--montage-scale", type=float, default=1.0)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--render-dpi", type=int, default=None,
                    help="PDF 渲染 dpi（默认=检测工作分辨率 150dpi；检测统一在 150dpi 当量做）")
    args = ap.parse_args()
    pages = parse_pages(args.pages)
    run_pages(args.pdf, pages, args.dpi, args.out, args.page_dir,
              args.montage, args.montage_scale, args.workers, args.render_dpi)


if __name__ == "__main__":
    main()
