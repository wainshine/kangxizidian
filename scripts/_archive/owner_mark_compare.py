#!/usr/bin/env python3
"""对 owner 标记的字逐个做「溯源切片对比」：成品字形 vs 原书同字墨迹裁片 + 页码/框 + 缺陷诊断。"""
import json, os, sys
import numpy as np, fitz
from PIL import Image, ImageDraw, ImageFont
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
FONT = os.path.join(ROOT, "release/KangXiKai-v2.4.15/KangXiKai-Regular-v2.4.15.ttf")
MAN = json.load(open(os.path.join(ROOT, "work/lead/manifest-v2415.json"), encoding="utf-8"))["chars"]
MP = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))


def glyph(ch, size=150):
    f = ImageFont.truetype(FONT, int(size * 0.8))
    im = Image.new("L", (size, size), 255)
    ImageDraw.Draw(im).text((size // 2, int(size * 0.92)), ch, font=f, fill=0, anchor="ms")
    return im


def src_crop(page, box, size=150):
    vol = page[:2]; pno = int(page[3:])
    doc = fitz.open(os.path.join(ROOT, "康熙字典", MP[vol]))
    pix = doc[pno - 1].get_pixmap(dpi=150, colorspace=fitz.csGRAY)
    g = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    doc.close()
    x0, y0 = max(0, box[0] - 4), max(0, box[1] - 4)
    x1, y1 = min(g.shape[1], box[2] + 4), min(g.shape[0], box[3] + 4)
    im = Image.fromarray(g[y0:y1, x0:x1])
    out = Image.new("L", (size, size), 255)
    s = min((size - 10) / im.width, (size - 10) / im.height)
    im2 = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))))
    out.paste(im2, ((size - im2.width) // 2, (size - im2.height) // 2))
    return out


def main():
    marks = json.load(open(os.path.join(ROOT, "work/review/owner-marks-extracted.json"), encoding="utf-8"))
    rows = []
    seen = set()
    for ver, sheets in marks.items():
        for sheet, picks in sheets.items():
            for p in picks:
                key = p["char"]
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"char": key, "from": f"{ver}/{sheet}/{p['cell']}",
                             "page": p["page"], "half": p["half"], "box": p["box"],
                             "in_current": p["in_current_v2415"]})
    # 生成拼图（每行 5 张卡：字形 + 原书裁片 + 标签）
    cols = 5
    cw, chh = 320, 250
    S = Image.new("L", (cols * cw, ((len(rows) + cols - 1) // cols) * chh), 255)
    d = ImageDraw.Draw(S)
    fnt = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 14)
    fch = ImageFont.truetype(FONT, 26)
    for i, r in enumerate(rows):
        x = (i % cols) * cw; y = (i // cols) * chh
        g = glyph(r["char"]); c = src_crop(r["page"], r["box"])
        S.paste(g, (x + 4, y + 4)); S.paste(c, (x + 160, y + 4))
        d.text((x + 4, y + 158), r["char"], font=fch, fill=0)
        d.text((x + 4, y + 190), f"{r['page']} {r['half']}", font=fnt, fill=0)
        d.text((x + 4, y + 208), f"box={r['box']}", font=fnt, fill=0)
        d.text((x + 4, y + 226), f"from {r['from']}  in={r['in_current']}", font=fnt, fill=0)
    out_png = os.path.join(ROOT, "work/review/owner-marks-compare.png")
    S.save(out_png)
    json.dump(rows, open(os.path.join(ROOT, "work/review/owner-marks-compare.json"), "w"),
              ensure_ascii=False, indent=1)
    print(json.dumps({"n": len(rows), "png": out_png,
                      "in_current": sum(1 for r in rows if r["in_current"])}))


if __name__ == "__main__":
    main()
