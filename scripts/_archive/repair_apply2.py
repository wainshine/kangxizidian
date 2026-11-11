#!/usr/bin/env python3
"""v2.4.15 外科修复：删除确认的缺陷组件（边栏直线 / 残片），其余轮廓保留。
输入：新 TTF + 待修字 list(json) + 输出 TTF。逐字重新识别组件后删除。"""
import json, os, sys
import numpy as np, cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
from refgate_clean import contour_to_points, contour_pixels, draw_contour


def analyze_comps(mask, total):
    """返回 {comp_id: kind}，kind in {line, frag, ok}。"""
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    out = {}
    for i in range(1, n):
        x, y, w, h, a = [int(v) for v in st[i]]
        if a < 25:
            out[i] = "frag"; continue
        comp = (lab == i)
        ys, xs = np.nonzero(comp)
        pts = np.column_stack([xs, ys]).astype(np.float32)
        vx, vy, x0, y0 = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01).ravel()
        dev = np.abs((pts[:, 0] - x0) * vy - (pts[:, 1] - y0) * vx)
        L = max(w, h); thick = a / max(1.0, L)
        line = L > 0.30 * 256 and thick <= 8 and float(dev.max()) < 5.0
        small = a < 0.025 * total
        if line:
            out[i] = "line"
        elif small and L > 0.06 * 256 and (L / max(1, min(w, h))) > 3.5:
            out[i] = "frag"
        else:
            out[i] = "ok"
    return lab, out


def main():
    font_path, targets_path, out_path = sys.argv[1:4]
    targets = set(json.load(open(targets_path, encoding="utf-8")))
    f = TTFont(font_path, recalcTimestamp=False)
    glyf = f["glyf"]; cmap = f.getBestCmap()
    stats = {"glyphs": 0, "dropped": {"line": 0, "frag": 0}}
    for ch in sorted(targets):
        cp = ord(ch)
        if cp not in cmap:
            continue
        gname = cmap[cp]
        contours = contour_to_points(glyf[gname])
        masks = [contour_pixels(p) for p in contours]
        # 逐轮廓判定（直线残片/碎片）
        areas = []
        for m in masks:
            if m is None:
                areas.append(0); continue
            _, _, local = m
            areas.append(int(local.sum()))
        total = sum(areas)
        if total == 0:
            continue
        drop = set()
        for j, m in enumerate(masks):
            if m is None or areas[j] < 25:
                if m is not None and areas[j] > 0 and areas[j] < 0.01 * total:
                    drop.add(j); stats["dropped"]["frag"] += 1
                continue
            x0, y0, local = m
            ys, xs = np.nonzero(local)
            pts = np.column_stack([xs, ys]).astype(np.float32)
            vx, vy, lx0, ly0 = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01).ravel()
            dev = np.abs((pts[:, 0] - lx0) * vy - (pts[:, 1] - ly0) * vx)
            bx0, bx1 = int(xs.min()), int(xs.max())
            by0, by1 = int(ys.min()), int(ys.max())
            L = max(bx1 - bx0 + 1, by1 - by0 + 1)
            thick = areas[j] / max(1.0, L)
            is_line = L > 0.30 * 256 and thick <= 8 and float(dev.max()) < 5.0
            small = areas[j] < 0.025 * total
            aspect = L / max(1.0, min(bx1 - bx0 + 1, by1 - by0 + 1))
            is_frag = (not is_line) and small and L > 15 and aspect > 3.5
            if is_line and areas[j] < 0.5 * total:
                drop.add(j); stats["dropped"]["line"] += 1
            elif is_frag and areas[j] < 0.5 * total:
                drop.add(j); stats["dropped"]["frag"] += 1
        if not drop:
            continue
        pen = TTGlyphPen(None)
        for j, pts in enumerate(contours):
            if j in drop:
                continue
            draw_contour(pen, pts)
        glyf[gname] = pen.glyph()
        stats["glyphs"] += 1
    f.save(out_path)
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
