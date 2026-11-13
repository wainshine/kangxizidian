#!/usr/bin/env python3
"""按参考结构闸结果做「字形级外科清理」：删除无参考对应的悬浮小组件轮廓，其余轮廓保留。

输入：TTF + refgate_scan_hi.jsonl（每字 suspects 的 256px 栅格 bbox）
输出：清理后的 TTF（轮廓级重建，字形其余部分不变）。
"""
import json, os, sys
import numpy as np, cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "work", "font", "_pylibs"))
from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen

SIZE = 256
BASELINE = int(0.88 * SIZE)


def contour_to_points(glyph):
    """返回 [[(x,y,on_curve), ...], ...]"""
    if glyph.numberOfContours <= 0:
        return []
    coords = glyph.coordinates
    flags = glyph.flags
    ends = glyph.endPtsOfContours
    out = []
    start = 0
    for e in ends:
        pts = []
        for i in range(start, e + 1):
            x, y = coords[i]
            f = flags[i]
            on = bool(f & 1)
            pts.append((float(x), float(y), on))
        out.append(pts)
        start = e + 1
    return out


def draw_contour(pen, pts):
    n = len(pts)
    if n < 3:
        return
    on_idx = [i for i, p in enumerate(pts) if p[2]]
    if not on_idx:
        # 全离线：以首尾中点为起点，插值全部为 qCurve
        x0 = (pts[0][0] + pts[-1][0]) / 2
        y0 = (pts[0][1] + pts[-1][1]) / 2
        pen.moveTo((x0, y0))
        for i in range(n):
            off = (pts[i][0], pts[i][1])
            nxt = pts[(i + 1) % n]
            mid = ((off[0] + nxt[0]) / 2, (off[1] + nxt[1]) / 2)
            pen.qCurveTo(off, mid)
        pen.closePath()
        return
    s = on_idx[0]
    pen.moveTo((pts[s][0], pts[s][1]))
    k = (s + 1) % n
    prev_off = None
    while k != s:
        x, y, on = pts[k]
        if on:
            if prev_off is not None:
                pen.qCurveTo(prev_off, (x, y))
                prev_off = None
            else:
                pen.lineTo((x, y))
        else:
            if prev_off is not None:
                mid = ((prev_off[0] + x) / 2, (prev_off[1] + y) / 2)
                pen.qCurveTo(prev_off, mid)
            prev_off = (x, y)
        k = (k + 1) % n
    if prev_off is not None:
        pen.qCurveTo(prev_off, (pts[s][0], pts[s][1]))
    pen.closePath()


def contour_pixels(pts, size=SIZE):
    scale = size / 1000.0
    # PIL 渲染单字 anchor="ms"：水平按 advance 居中（advance=UPM → 原点=0），垂直按 baseline
    px = [(p[0] * scale, BASELINE - p[1] * scale) for p in pts]
    xs = [p[0] for p in px]; ys = [p[1] for p in px]
    x0, x1 = int(np.floor(min(xs))), int(np.ceil(max(xs))) + 1
    y0, y1 = int(np.floor(min(ys))), int(np.ceil(max(ys))) + 1
    if x1 <= x0 or y1 <= y0:
        return None
    local = np.zeros((y1 - y0, x1 - x0), np.uint8)
    poly = np.array([[int(round(x - x0)), int(round(y - y0))] for x, y in px], np.int32)
    cv2.fillPoly(local, [poly], 1)
    return (x0, y0, local)


def main():
    font_path = sys.argv[1]
    scan_path = sys.argv[2]
    out_path = sys.argv[3]
    suspects = {}
    for line in open(scan_path, encoding="utf-8"):
        r = json.loads(line)
        if r.get("major"):
            continue
        suspects[r["char"]] = [s["bbox"] for s in r["suspects"]]
    f = TTFont(font_path, recalcTimestamp=False)
    glyf = f["glyf"]
    cmap = f.getBestCmap()
    n_clean = 0
    for ch, bboxes in suspects.items():
        if ord(ch) not in cmap:
            continue
        gname = cmap[ord(ch)]
        glyph = glyf[gname]
        contours = contour_to_points(glyph)
        if not contours:
            continue
        # 预计算每条轮廓的像素数与总墨量
        all_cp = [contour_pixels(p) for p in contours]
        all_px = [(0 if cp is None else int(np.count_nonzero(cp[2]))) for cp in all_cp]
        glyph_px = sum(all_px)
        keep, dropped = [], 0
        dropped_px = 0
        total_px = 0
        for ci, pts in enumerate(contours):
            cp = all_cp[ci]
            if cp is None:
                keep.append(pts); continue
            cx0, cy0, local = cp
            ly, lx = np.nonzero(local)
            if len(lx) == 0:
                keep.append(pts); continue
            # 该轮廓像素落入 suspect bbox 的比例
            inside = 0
            for xx, yy in zip(lx, ly):
                gx, gy = xx + cx0, yy + cy0
                for (a, b, c, d) in bboxes:
                    if a <= gx <= c and b <= gy <= d:
                        inside += 1
                        break
            frac = inside / len(lx)
            total_px += len(lx)
            if frac >= 0.5 and len(lx) <= 0.02 * SIZE * SIZE and all_px[ci] <= 0.06 * glyph_px:
                dropped += 1
                dropped_px += len(lx)
            else:
                keep.append(pts)
        if dropped == 0:
            continue
        if not keep:
            continue
        # 安全阀：删掉的墨量不超过字形总墨量 40%（否则说明判据失效，跳过）
        if total_px > 0 and dropped_px > 0.40 * total_px:
            continue
        pen = TTGlyphPen(None)
        for pts in keep:
            draw_contour(pen, pts)
        glyf[gname] = pen.glyph()
        n_clean += 1
    f.save(out_path)
    print(json.dumps({"cleaned_glyphs": n_clean, "out": out_path}))


if __name__ == "__main__":
    main()
