#!/usr/bin/env python3
"""锚点体检对比图：原书裁片上叠加 ①2×2 格块（灰）②锚点原框（红=被切/绿=正常）③修复后锚点框（绿虚线）④当前字体框（蓝）。"""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from grid_cut_v2 import page_gray
FONT = os.path.join(ROOT, "release/KangXiKai-v2.4.15/KangXiKai-Regular-v2.4.15.ttf")
MAN = json.load(open(os.path.join(ROOT, "work/lead/manifest-v2415.json"), encoding="utf-8"))["chars"]


def glyph_img(ch, size=120):
    f = ImageFont.truetype(FONT, int(size * 0.8))
    im = Image.new("L", (size, size), 255)
    ImageDraw.Draw(im).text((size // 2, int(size * 0.92)), ch, fill=0, font=f, anchor="ms")
    return im


def main():
    rows = json.load(open(os.path.join(ROOT, "work/review/anchors-repaired.json"), encoding="utf-8"))
    pages = {}
    cols, cw, chh = 5, 300, 410
    nrows = (len(rows) + cols - 1) // cols
    S = Image.new("RGB", (cols * cw, nrows * chh), (255, 255, 255))
    d = ImageDraw.Draw(S)
    fnt = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 12)
    fch = ImageFont.truetype(FONT, 20)
    for i, r in enumerate(rows):
        page = r["page"]
        if page not in pages:
            pages[page] = page_gray(page[:2], int(page[3:]))
        g = pages[page]
        ab = r["box"]; rb = r.get("repaired_box") or ab; block = r.get("block")
        # 显示范围：锚点 + 格块 + 1 格余量
        x0 = min(ab[0], rb[0], *( [block[0]] if block else [ab[0]])) - 45
        y0 = min(ab[1], rb[1], *( [block[1]] if block else [ab[1]])) - 45
        x1 = max(ab[2], rb[2], *( [block[2]] if block else [ab[2]])) + 45
        y1 = max(ab[3], rb[3], *( [block[3]] if block else [ab[3]])) + 45
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(g.shape[1], x1), min(g.shape[0], y1)
        sub = Image.fromarray(g[y0:y1, x0:x1]).convert("RGB")
        size = 190
        sub = sub.resize((size, size))
        sx, sy = size / max(1, x1 - x0), size / max(1, y1 - y0)
        dr = ImageDraw.Draw(sub)
        def rect(b, color, width=2, dash=False):
            b = [int((b[0] - x0) * sx), int((b[1] - y0) * sy), int((b[2] - x0) * sx), int((b[3] - y0) * sy)]
            if not dash:
                dr.rectangle(b, outline=color, width=width)
            else:
                xa, ya, xb, yb = b
                step = 6
                for x in range(xa, xb, step):
                    dr.line([x, ya, min(x + step // 2, xb), ya], fill=color, width=width)
                    dr.line([x, yb, min(x + step // 2, xb), yb], fill=color, width=width)
                for y in range(ya, yb, step):
                    dr.line([xa, y, xa, min(y + step // 2, yb)], fill=color, width=width)
                    dr.line([xb, y, xb, min(y + step // 2, yb)], fill=color, width=width)
        if block:
            rect(block, (140, 140, 140))
        anchor_color = (200, 0, 0) if r["status"] == "cut" else (0, 160, 0)
        rect(ab, anchor_color)
        if rb != ab:
            rect(rb, (0, 110, 0), 2, dash=True)
        cur = MAN.get(r["char"])
        if cur and cur["page"] == page:
            rect(cur["box"], (0, 90, 220))
        x = (i % cols) * cw; y = (i // cols) * chh
        S.paste(sub, (x + 55, y + 4))
        S.paste(glyph_img(r["char"]), (x + 85, y + 198))
        d.text((x + 4, y + 200), r["char"], font=fch, fill=(0, 0, 0))
        d.text((x + 4, y + 224), f'{r["set"]} {r["page"]} {r["half"]}', font=fnt, fill=(0, 0, 0))
        d.text((x + 4, y + 238), f'anchor={ab}', font=fnt, fill=anchor_color)
        if rb != ab:
            d.text((x + 4, y + 252), f'repaired={rb}', font=fnt, fill=(0, 110, 0))
        if r.get("block"):
            d.text((x + 4, y + 266), f'cell2x2={r["block"]}', font=fnt, fill=(110, 110, 110))
        lat = r.get("lattice") or {}
        d.text((x + 4, y + 280), f'px={lat.get("px")} py={lat.get("py")}', font=fnt, fill=(0, 0, 0))
        d.text((x + 4, y + 294), f'status={r["status"]}', font=fnt,
               fill=(200, 0, 0) if r["status"] == "cut" else (0, 150, 0))
    out = os.path.join(ROOT, "work/review/anchors-check.png")
    S.save(out)
    print(json.dumps({"png": out, "n": len(rows)}))


if __name__ == "__main__":
    main()
