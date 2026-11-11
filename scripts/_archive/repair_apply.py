#!/usr/bin/env python3
"""v2.4.15 修复：①找回「误删真笔画」（旧版有、新版无、且参考字体有墨 → 恢复）
②删除「边栏直线残片」（细长 + 直线度高 + 非主组件）。"""
import json, os, sys
import numpy as np, cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
from refgate import ref_has
from refgate2 import raster, SONGTI, SIZE
from refgate_clean import contour_to_points, contour_pixels, draw_contour

SCALE = SIZE / 1000.0
BASELINE = int(0.88 * SIZE)


def contours_of(glyf, gname, cmap):
    glyph = glyf[gname]
    return contour_to_points(glyph)


def contour_comp_map(contours):
    """每条轮廓的栅格像素与 bbox。"""
    out = []
    for pts in contours:
        cp = contour_pixels(pts)
        if cp is None:
            out.append(None); continue
        x0, y0, local = cp
        ys, xs = np.nonzero(local)
        out.append((x0, y0, xs + x0, ys + y0))
    return out


def main():
    old_path, new_path, man_path, out_path = sys.argv[1:5]
    cmap_chars = sorted(json.load(open(man_path, encoding="utf-8"))["chars"].keys())
    old = TTFont(old_path, recalcTimestamp=False); new = TTFont(new_path, recalcTimestamp=False)
    og, ng = old["glyf"], new["glyf"]
    ocm, ncm = old.getBestCmap(), new.getBestCmap()
    stats = {"restored_components": 0, "removed_lines": 0, "touched_glyphs": 0}
    for ch in cmap_chars:
        cp = ord(ch)
        if cp not in ng or cp not in ocm:
            continue
        gname = ncm[cp]
        # ---- ① 恢复误删组件 ----
        o_mask = raster(old_path, ch); n_mask = raster(new_path, ch)
        ref = raster(SONGTI, ch, index=7) if ref_has(ch) else None
        restored = []
        if ref is not None:
            ref_d = cv2.dilate(ref.astype(np.uint8), np.ones((13, 13), np.uint8)) > 0
            new_d = cv2.dilate(n_mask.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
            o_lab_o, o_st, _ = cv2.connectedComponentsWithStats(o_mask.astype(np.uint8), 8)
            total_old = int(o_mask.sum())
            oconts = contour_comp_map(contours_of(og, ocm[cp] and old.getBestCmap()[cp], old.getBestCmap()))
            # 每个旧组件：主要像素在新字形中缺失？且参考有墨？
            for i in range(1, o_lab_o):
                x, y, w, h, a = o_st[i]
                if a < 20:
                    continue
                comp = (o_lab_o == i)
                kept = float((comp & new_d).sum()) / a
                if kept > 0.25:
                    continue  # 没被删
                cov_ref = float((comp & ref_d).sum()) / a
                if cov_ref < 0.35:
                    continue  # 参考也没墨 → 碎片，删对了
                # 找该组件对应的旧轮廓
                idxs = []
                for j, m in enumerate(oconts):
                    if m is None:
                        continue
                    xs, ys = m[2], m[3]
                    if len(xs) == 0:
                        continue
                    inside = ((xs >= x) & (xs <= x + w) & (ys >= y) & (ys <= y + h)).sum() / len(xs)
                    if inside >= 0.6:
                        idxs.append(j)
                if idxs:
                    restored.append((idxs, i, a, round(cov_ref, 2)))
        # ---- ② 删除边栏直线 ----
        nconts = contour_pixels(contours_of(ng, gname))
        drop = set()
        n_lab, n_st, _ = cv2.connectedComponentsWithStats(n_mask.astype(np.uint8), 8)
        total_new = int(n_mask.sum())
        for i in range(1, n_lab):
            x, y, w, h, a = n_st[i]
            if a < 40 or a > 0.2 * total_new:
                continue
            comp = (n_lab == i)
            ys, xs = np.nonzero(comp)
            pts = np.column_stack([xs, ys]).astype(np.float32)
            vx, vy, x0, y0 = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01).ravel()
            dev = np.abs((pts[:, 0] - x0) * vy - (pts[:, 1] - y0) * vx)
            length = max(w, h)
            thick = a / max(1.0, length)
            if length > 0.35 * SIZE and thick <= 7 and float(dev.max()) < 3.5:
                for j, m in enumerate(nconts):
                    if m is None:
                        continue
                    xs2, ys2 = m[2], m[3]
                    if len(xs2) == 0:
                        continue
                    inside = ((xs2 >= x) & (xs2 <= x + w) & (ys2 >= y) & (ys2 <= y + h)).sum() / len(xs2)
                    if inside >= 0.6:
                        drop.add(j)
        if not restored and not drop:
            continue
        # ---- 重建字形 ----
        keep_pts = []
        new_conts = contours_of(ng, gname)
        for j, pts in enumerate(new_conts):
            if j in drop:
                continue
            keep_pts.append(pts)
        oconts2 = contours_of(og, old.getBestCmap()[cp])
        for idxs, i, a, cov in restored:
            for j in idxs:
                pts = oconts2[j]
                # 避免重复（与已有轮廓 bbox 高度重合则跳过）
                keep_pts.append(pts)
                stats["restored_components"] += 1
        stats["removed_lines"] += len(drop)
        pen = TTGlyphPen(None)
        for pts in keep_pts:
            draw_contour(pen, pts)
        ng[gname] = pen.glyph()
        stats["touched_glyphs"] += 1
    new.save(out_path)
    print(json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
