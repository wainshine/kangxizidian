#!/usr/bin/env python3
"""后处理：把每个字形的墨迹 bbox 长边统一缩放到 760 units，中心置于 (500,400)。
修复「框含边距导致字形被缩小」的问题（v2.4.8）。用 TTGlyphPen + TransformPen 重绘。
用法: python scripts/postscale_glyphs.py --font <in.ttf> --out <out.ttf>
"""
import argparse, sys
sys.path.insert(0, "work/font/_pylibs")
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.transformPen import TransformPen

TARGET = 760.0
CX, CY = 500.0, 400.0


def rescale(font_path, out_path):
    f = TTFont(font_path)
    gs = f.getGlyphSet()
    glyf = f["glyf"]
    changed = 0
    for gname in f.getGlyphOrder():
        gl = glyf[gname]
        if gl.numberOfContours <= 0:
            continue
        bp = BoundsPen(gs)
        gs[gname].draw(bp)
        if not bp.bounds:
            continue
        x0, y0, x1, y1 = bp.bounds
        w, h = x1 - x0, y1 - y0
        if w <= 0 or h <= 0:
            continue
        s = TARGET / max(w, h)
        if abs(s - 1.0) < 0.004:
            continue
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        tx = CX - cx * s
        ty = CY - cy * s
        tpen = TTGlyphPen(None)
        gs[gname].draw(TransformPen(tpen, (s, 0, 0, s, tx, ty)))
        glyf[gname] = tpen.glyph()
        changed += 1
    f.save(out_path)
    print("rescaled", changed, "glyphs ->", out_path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rescale(args.font, args.out)
