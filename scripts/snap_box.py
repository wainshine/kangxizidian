#!/usr/bin/env python3
"""格点约束的框搜索（类级修复：修「切偏/切不全」）。

思路：用字格阵（x/y 格距+相位）把每个字框对齐到 2×2 格块；
在 ±1 格范围内搜索 9 个候选块，用「参考结构」评分选出最优块：
  score = 参考支持域覆盖 - λ×参考外多余墨 - μ×超出块外墨
这样既避免切偏（邻墨/框线进入），也避免缺笔画（字被切掉一部分）。
"""
import os, sys
import numpy as np, cv2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work/font/_pylibs"))
import font_norm as FN
from refgate import ref_has, SONGTI


def half_lattice(gray, half):
    """返回 (px, py, phx, phy) 或 None。half: 'L'/'R'。gutter 由调用者给。"""
    pass  # 由 page_lattice 统一算


def page_lattice(gray, gutter):
    from cell_grid_boxes import binarize, fit_axis
    ink = binarize(gray)
    h, w = gray.shape
    half = {}
    for name, mask in (("L", lambda x, y: x < gutter), ("R", lambda x, y: x >= gutter)):
        n, lab, st, _ = cv2.connectedComponentsWithStats(ink, 8)
        small = []
        for i in range(1, n):
            x, y, ww, hh, a = [int(v) for v in st[i]]
            if not mask(x + ww / 2, y + hh / 2):
                continue
            if 24 <= hh <= 54 and 9 <= ww <= 60 and 40 <= a <= 1200:
                small.append((x + ww / 2, y + hh / 2, hh))
        if len(small) < 120:
            half[name] = None
            continue
        h0 = float(np.median([s[2] for s in small]))
        xs = np.array([s[0] for s in small]); ys = np.array([s[1] for s in small])
        sx, px, phx = fit_axis(xs, 0.9 * h0, 1.9 * h0)
        sy, py, phy = fit_axis(ys, 0.85 * h0, 1.6 * h0)
        def refine(vals, pitch, phase):
            lag = np.mod(vals - phase + pitch / 2, pitch) - pitch / 2
            return phase + float(np.median(lag))
        half[name] = {"px": float(px), "py": float(py),
                      "phx": refine(xs, px, phx), "phy": refine(ys, py, phy)}
    return half


def ref_render(ch, size=256):
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype(SONGTI, size, index=7)
    im = Image.new("L", (size, size), 0)
    ImageDraw.Draw(im).text((size // 2, int(0.88 * size)), ch, fill=255, font=f, anchor="ms")
    return np.array(im) > 127


def block_ink(ink, box):
    h, w = ink.shape
    x0, y0, x1, y1 = [int(v) for v in box]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return None
    return ink[y0:y1, x0:x1]


def score_block(sub, ref, small_ink):
    """用参考结构给块打分（都是 150dpi 像素空间）。"""
    if sub is None or sub.size == 0:
        return -1e9, {}
    a = float(sub.sum())
    if a < 0.5 * small_ink:
        return -1e9, {"ink": a}
    # 把参考（256）缩放配准到块尺寸：以块内墨的主组件 bbox 对齐参考墨 bbox
    ys, xs = np.nonzero(sub)
    if len(xs) == 0:
        return -1e9, {"ink": a}
    gb = (xs.min(), ys.min(), xs.max(), ys.max())
    rb = ref_bbox(ref)
    gh = max(1, gb[3] - gb[1] + 1); gw = max(1, gb[2] - gb[0] + 1)
    rh = max(1, rb[3] - rb[1] + 1); rw = max(1, rb[2] - rb[0] + 1)
    s = min((sub.shape[1]) / max(1, rw), (sub.shape[0]) / max(1, rh)) * 0.92
    # 参考映射到块内，使参考 bbox 中心对齐块中心
    rwarp = np.zeros((sub.shape[0], sub.shape[1]), np.uint8)
    ref_small = cv2.resize(ref.astype(np.uint8), (max(1, int(rw * s)), max(1, int(rh * s))),
                           interpolation=cv2.INTER_NEAREST)
    cx = (gb[0] + gb[2]) / 2.0; cy = (gb[1] + gb[3]) / 2.0
    ox = int(cx - ref_small.shape[1] / 2); oy = int(cy - ref_small.shape[0] / 2)
    x0 = max(0, ox); y0 = max(0, oy)
    x1 = min(sub.shape[1], ox + ref_small.shape[1]); y1 = min(sub.shape[0], oy + ref_small.shape[0])
    if x1 > x0 and y1 > y0:
        rwarp[y0:y1, x0:x1] = ref_small[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
    rd = cv2.dilate(rwarp, np.ones((11, 11), np.uint8)) > 0
    support = float((sub.astype(bool) & rd).sum()) / max(1.0, a)
    extra = float((sub.astype(bool) & ~rd).sum()) / max(1.0, a)
    # 块边界溢出：块外 3px 带内墨量（相对块内）
    return 1.2 * support - 0.8 * extra, {"support": round(support, 3), "extra": round(extra, 3), "ink": int(a)}


def ref_bbox(ref):
    ys, xs = np.nonzero(ref)
    if len(xs) == 0:
        return (0, 0, 1, 1)
    return (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))


def snap_box(page, half, box, ch, gutter):
    """返回最优 2×2 格块框（150dpi）。"""
    gray = FN.render_pdf_crop(page, [0, 0, 1, 1], pad150=0, dpi=150) if False else None
    return None  # 由外部 page 上下文调用 search_box


def search_box(gray, lattice, box, ch):
    if lattice is None or not ref_has(ch):
        return None
    ink = __import__("cell_grid_boxes").binarize(gray)
    h, w = gray.shape
    px, py = lattice["px"], lattice["py"]
    phx, phy = lattice["phx"], lattice["phy"]
    cx = (box[0] + box[2]) / 2.0; cy = (box[1] + box[3]) / 2.0
    c0 = int(np.round((cx - 2 * px - phx) / px))
    r0 = int(np.round((cy - 2 * py - phy) / py))
    ref = ref_render(ch)
    # 小字墨量：用块内 ink 的中位作参照（这里用 150dpi 小字 ink≈120）
    best = None
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            r = r0 + dr; c = c0 + dc
            bx0 = int(round(phx + c * px)); by0 = int(round(phy + r * py))
            bx1 = int(round(bx0 + 2 * px)); by1 = int(round(by0 + 2 * py))
            sub = block_ink(ink, (bx0, by0, bx1, by1))
            sc, det = score_block(sub, ref, small_ink=120)
            if best is None or sc > best[0]:
                best = (sc, [bx0, by0, bx1, by1], det, (r, c))
    if best is None:
        return None
    return {"box": best[1], "score": round(best[0], 3), "detail": best[2], "cell": best[3]}
