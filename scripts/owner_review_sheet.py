#!/usr/bin/env python3
"""生成 owner 审核表：100 字 provenance 核验（成品字形 + 原书墨迹裁片 + 页码/框 + 来源标签）。

用途：owner 逐字确认「① 是对应字的真迹（非注文/GAN/拼接）② 无污染/边角料 ③ 无缺笔」。
输出：work/review/owner-provenance-100.html（可点开看原图）+ 同名 PNG 拼图（单元格编号）。
"""
import json, os, sys, base64, random, io
import numpy as np, fitz
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_font():
    return "release/KangXiKai-v2.4.15/KangXiKai-Regular-v2.4.15.ttf"


def glyph_png(font_path, ch, size=160):
    f = ImageFont.truetype(font_path, int(size * 0.8))
    im = Image.new("L", (size, size), 255)
    ImageDraw.Draw(im).text((size // 2, int(size * 0.9)), ch, font=f, fill=0, anchor="ms")
    return im


def crop_png(page, box, dpi=150, pad=6):
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    vol = page[:2]; pno = int(page[3:])
    doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
    pix = doc[pno - 1].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    g = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    doc.close()
    x0, y0 = max(0, box[0] - pad), max(0, box[1] - pad)
    x1, y1 = min(g.shape[1], box[2] + pad), min(g.shape[0], box[3] + pad)
    im = Image.fromarray(g[y0:y1, x0:x1]).convert("L")
    out = Image.new("L", (160, 160), 255)
    im.thumbnail((150, 150))
    out.paste(im, ((160 - im.width) // 2, (160 - im.height) // 2))
    return out


def main():
    font = load_font()
    man = json.load(open(os.path.join(ROOT, "work/lead/manifest-v2415.json"), encoding="utf-8"))
    chars = man["chars"]
    # 只抽基本区字（U+4E00–U+9FFF）：owner 可读、参考字体/PIL 渲染稳定
    basic = [c for c in sorted(chars) if 0x4E00 <= ord(c) <= 0x9FFF]
    random.seed(2026)
    sample = random.sample(basic, min(100, len(basic)))
    os.makedirs(os.path.join(ROOT, "work/review"), exist_ok=True)
    rows = []
    for i, ch in enumerate(sample, 1):
        r = chars[ch]
        rows.append({"no": i, "char": ch, "page": r["page"], "half": r.get("half", ""),
                     "box": r["box"], "label_source": r.get("label_source", "")})
    # HTML
    html = ["<html><head><meta charset='utf-8'><style>",
            "body{font-family:-apple-system,sans-serif;margin:20px}",
            "table{border-collapse:collapse}td{border:1px solid #ccc;padding:4px;text-align:center;font-size:13px}",
            "img{display:block}</style></head><body>",
            "<h2>Owner provenance 核验表（100 字，v2.4.15）</h2>",
            "<p>每格：左=成品字形；中=原书同字墨迹裁片；下方为 编号/字/页码-框/来源标签。",
            "请逐字确认：① 是该字的真迹墨迹（非注文、非 GAN、非拼接）；② 无框线/邻字残片；③ 无缺笔。</p>",
            "<table>"]
    for r in rows:
        g = glyph_png(font, r["char"])
        c = crop_png(r["page"], r["box"])
        b1 = io.BytesIO(); g.save(b1, "PNG")
        b2 = io.BytesIO(); c.save(b2, "PNG")
        d1 = base64.b64encode(b1.getvalue()).decode(); d2 = base64.b64encode(b2.getvalue()).decode()
        html.append("<tr>")
        html.append(f"<td><img src='data:image/png;base64,{d1}'></td>")
        html.append(f"<td><img src='data:image/png;base64,{d2}'></td>")
        html.append(f"<td>#{r['no']}<br>{r['char']}<br>{r['page']} {r['half']}<br>box={r['box']}<br>{r['label_source']}</td>")
        html.append("</tr>")
    html.append("</table></body></html>")
    out_html = os.path.join(ROOT, "work/review/owner-provenance-100.html")
    open(out_html, "w", encoding="utf-8").write("\n".join(html))
    # PNG 拼图（带编号）
    cols = 10
    cw, chh = 190, 320
    S = Image.new("L", (cols * cw, ((len(rows) + cols - 1) // cols) * chh), 255)
    d = ImageDraw.Draw(S)
    try:
        fnt = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 16)
    except Exception:
        fnt = ImageFont.load_default()
    # 字头用本项目字体绘制（覆盖生僻字，避免 Hiragino 缺字豆腐块）
    fnt_ch = ImageFont.truetype(font, 24)
    for i, r in enumerate(rows):
        x = (i % cols) * cw; y = (i // cols) * chh
        g = glyph_png(font, r["char"], 110)
        c = crop_png(r["page"], r["box"])
        S.paste(g, (x + 35, y + 2))
        d.text((x + 4, y + 114), f"#{r['no']}", font=fnt, fill=0)
        d.text((x + 30, y + 106), r['char'], font=fnt_ch, fill=0)
        S.paste(c, (x + 35, y + 142))
        d.text((x + 4, y + 258), f"{r['page']} {r['half']}", font=fnt, fill=0)
        d.text((x + 4, y + 278), f"{r['box']}", font=fnt, fill=0)
    out_png = os.path.join(ROOT, "work/review/owner-provenance-100.png")
    S.save(out_png)
    json.dump(rows, open(os.path.join(ROOT, "work/review/owner-provenance-100.json"), "w"),
              ensure_ascii=False, indent=1)
    print(json.dumps({"html": out_html, "png": out_png, "n": len(rows)}))


if __name__ == "__main__":
    main()
