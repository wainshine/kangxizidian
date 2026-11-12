#!/usr/bin/env python3
"""生成彩色版 owner 核验表：字形/原书裁片保持灰阶（扫描本身无彩色），编目信息用彩色区分。"""
import json, os, sys
import numpy as np, fitz
from PIL import Image, ImageDraw, ImageFont
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.environ.get("OWNER_FONT", os.path.join(ROOT, "work/font/build/KangXiKai-v2.5.8.ttf"))
MP = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
rows = json.load(open(os.path.join(ROOT, "work/review/owner-provenance-100-v258.json")))


def page_gray(page):
    vol = page[:2]; pno = int(page[3:])
    doc = fitz.open(os.path.join(ROOT, "康熙字典", MP[vol]))
    pix = doc[pno - 1].get_pixmap(dpi=150, colorspace=fitz.csGRAY)
    g = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    doc.close()
    return g


def glyph(ch, size=110):
    f = ImageFont.truetype(FONT, int(size * 0.8))
    im = Image.new("L", (size, size), 255)
    ImageDraw.Draw(im).text((size // 2, int(size * 0.92)), ch, fill=0, font=f, anchor="ms")
    return im


def crop(page, box, size=110):
    g = page_gray(page)
    x0, y0 = max(0, box[0] - 4), max(0, box[1] - 4)
    x1, y1 = min(g.shape[1], box[2] + 4), min(g.shape[0], box[3] + 4)
    im = Image.fromarray(g[y0:y1, x0:x1])
    out = Image.new("L", (size, size), 255)
    s = min((size - 8) / im.width, (size - 8) / im.height)
    im2 = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))))
    out.paste(im2, ((size - im2.width) // 2, (size - im2.height) // 2))
    return out


def main():
    fnt = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 14)
    fch = ImageFont.truetype(FONT, 26)
    cols, cw, chh = 10, 190, 330
    S = Image.new("RGB", (cols * cw, ((len(rows) + cols - 1) // cols) * chh), (255, 255, 255))
    d = ImageDraw.Draw(S)
    pages = {}
    for i, r in enumerate(rows):
        x = (i % cols) * cw; y = (i // cols) * chh
        d.rectangle([x, y, x + cw - 1, y + chh - 1], outline=(210, 210, 210))
        S.paste(glyph(r["char"]), (x + 40, y + 2))
        d.text((x + 4, y + 112), f'#{r["no"]}', font=fnt, fill=(200, 0, 0))
        d.text((x + 32, y + 104), r["char"], font=fch, fill=(0, 0, 0))
        page = r["page"]
        if page not in pages:
            pages[page] = page_gray(page)
        S.paste(crop(page, r["box"]), (x + 40, y + 140))
        d.text((x + 4, y + 254), f'{page} {r["half"]}', font=fnt, fill=(0, 110, 200))
        d.text((x + 4, y + 272), f'框={r["box"]}', font=fnt, fill=(0, 140, 0))
        d.text((x + 4, y + 290), f'{r["label_source"]}'[:26], font=fnt, fill=(120, 120, 120))
    out = os.path.join(ROOT, "work/review/owner-provenance-100-v258-color.png")
    S.save(out)
    print(json.dumps({"png": out, "n": len(rows), "mode": "RGB"}))


if __name__ == "__main__":
    main()
