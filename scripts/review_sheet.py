#!/usr/bin/env python3
"""复核表版式公共库（owner-provenance 版式）——被 owner_review_sheet.py 与 make_round_pack.py 共用。

版式（与 2026-11 的 owner-provenance-100 完全一致）：
  每格 190×320：上=最终字形（110px），中=编号/字/页/框，下=原书裁片（160px）。
  HTML 版：左=字形、中=裁片、右=文字（由调用方组装）。

设计原则：**不要复制版式代码**；本文件是唯一实现，脚本只做数据准备。
"""
import json, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PAGE_CACHE = {}

# 参照字体：用于「Unicode 身份标签/对照小字」，必须独立于项目字体（否则自举死循环）。
# 唯一来源 scripts/reffont.py：霞鹜文楷（OFL）；禁止系统宋体/黑体（DECISIONS D21）。
from reffont import path as _ref_path, has_cp as _ref_has_cp  # noqa: E402


def ref_font_path():
    return _ref_path()


def ref_has_char(ch):
    """参照字体是否覆盖该字符（稀有扩展字可能没有 → 明确标注，不画豆腐块）。"""
    return _ref_has_cp(ord(ch))


def pdf_map():
    return json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))


def page_gray(page, dpi=150):
    key = (page, dpi)
    if key in _PAGE_CACHE:
        return _PAGE_CACHE[key]
    import fitz
    mp = pdf_map()
    doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[page[:2]]))
    pix = doc[int(page[3:]) - 1].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    g = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    doc.close()
    _PAGE_CACHE.clear()
    _PAGE_CACHE[key] = g
    return g


def crop_png(page, box, size=160, pad=6, dpi=150):
    g = page_gray(page, dpi)
    # mapping 的 box 可能是 float（150dpi 坐标）；统一取整后再切片
    bx = [int(round(v)) for v in box]
    x0, y0 = max(0, bx[0] - pad), max(0, bx[1] - pad)
    x1, y1 = min(g.shape[1], bx[2] + pad), min(g.shape[0], bx[3] + pad)
    im = Image.fromarray(g[y0:y1, x0:x1]).convert("L")
    out = Image.new("L", (size, size), 255)
    im.thumbnail((size - 10, size - 10))
    out.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    return out


def glyph_png(font, ch, size=160):
    """font 可为路径或 ImageFont 对象。"""
    if isinstance(font, str):
        f = ImageFont.truetype(font, int(size * 0.8))
    else:
        f = font
    im = Image.new("L", (size, size), 255)
    ImageDraw.Draw(im).text((size // 2, int(size * 0.9)), ch, font=f, fill=0, anchor="ms")
    return im


def labels(scale=1.0):
    """标签字体：数字/页码/框/类别 + **小字参照字形**统一用 OFL 参照字体。"""
    ref = ref_font_path()
    lab = ImageFont.truetype(ref, max(10, int(14 * scale)))
    chf = ImageFont.truetype(ref, max(14, int(26 * scale)))
    return lab, chf


def _draw_fit(draw, xy, text, font, fill, max_w):
    """按格宽自动缩字号，避免长文本（如 框=[...]）溢出到邻格。"""
    f = font
    while draw.textlength(text, font=f) > max_w and getattr(f, "size", 0) > 8:
        f = ImageFont.truetype(f.path, f.size - 1)
    draw.text(xy, text, font=f, fill=fill)


def draw_cell(canvas, x, y, row, font_path, cell_w=200, cell_h=290, scale=1.0, color=False):
    """一格三要素（互不重叠）：

      左上大字 = **成品字形**（项目字体，被审对象）
      右上小字 + U+码位 = **Unicode 参照字形**（霞鹜文楷 OFL，独立字体，避免自举）
      下方 = **原书裁片**
      底部 = 页码/框/来源

    owner-provenance 版式；scale 用于 2× 大图。
    """
    s = scale
    lab, chf = labels(s)                     # 均来自 OFL 参照字体
    d = ImageDraw.Draw(canvas)
    if color:
        d.rectangle([x, y, x + int(cell_w) - 1, y + int(cell_h) - 1], outline=(210, 210, 210))
        c_no = (200, 0, 0); c_ch = (0, 0, 0); c_pg = (0, 110, 200)
        c_bx = (0, 140, 0); c_src = (120, 120, 120); c_ref = (0, 0, 0)
    else:
        c_no = 0; c_ch = 0; c_pg = 0; c_bx = 0; c_src = 120; c_ref = 0
    # 左上：成品字形
    g = glyph_png(font_path, row["char"], int(110 * s)).convert("RGB" if color else "L")
    canvas.paste(g, (x + int(8 * s), y + int(4 * s)))
    # 右上：编号 + U+码位 + 参照字形（霞鹜文楷）
    codepoint = f"U+{ord(row['char']):04X}" if len(row["char"]) == 1 else ""
    d.text((x + int(124 * s), y + int(6 * s)), f"#{row.get('no','')}", font=lab, fill=c_no)
    d.text((x + int(124 * s), y + int(24 * s)), codepoint, font=lab, fill=c_src)
    if ref_has_char(row["char"]):
        _ref_glyph = glyph_png(ref_font_path(), row["char"], int(48 * s)).resize(
            (max(1, int(48 * s)), max(1, int(56 * s))))
        canvas.paste(_ref_glyph.convert("RGB" if color else "L"), (x + int(126 * s), y + int(38 * s)))
    else:
        d.text((x + int(126 * s), y + int(46 * s)), "无参照", font=lab, fill=(160, 160, 160))
    # 下方：原书裁片
    c = crop_png(row["page"], row["box"], int(110 * s), pad=4).convert("RGB" if color else "L")
    canvas.paste(c, (x + int(8 * s), y + int(122 * s)))
    # 底部三行
    maxw = cell_w - int(8 * s)
    _draw_fit(d, (x + int(8 * s), y + int(238 * s)), f"{row['page']} {row.get('half','')}", lab, c_pg, maxw)
    _draw_fit(d, (x + int(8 * s), y + int(256 * s)), f"框={row['box']}", lab, c_bx, maxw)
    src = str(row.get("label_source") or row.get("class") or "")[:26]
    _draw_fit(d, (x + int(8 * s), y + int(274 * s)), src, lab, c_src, maxw)
    return canvas


def build_sheet(rows, font_path, out_png, cols=10, cell=(200, 290), per_page=100, scale=1.0,
                color=False):
    """按 owner-provenance 版式输出 PNG；out_png 可为含 {n} 的模板。"""
    pages = [rows[i:i + per_page] for i in range(0, len(rows), per_page)] or [[]]
    cw = int(round(cell[0] * scale)); chh = int(round(cell[1] * scale))  # 画布格位也随 scale 放大
    outs = []
    for pi, page_rows in enumerate(pages):
        nrows = max(1, (len(page_rows) + cols - 1) // cols)
        S = Image.new("RGB" if color else "L", (cols * cw, nrows * chh),
                      (255, 255, 255) if color else 255)
        for i, r in enumerate(page_rows):
            draw_cell(S, (i % cols) * cw, (i // cols) * chh, r, font_path,
                      cw, chh, scale, color)
        path = out_png.format(pi + 1) if "{" in out_png else out_png
        S.save(path)
        outs.append(path)
    return outs


def write_tsv(rows, path, fields=("no", "char", "page", "half", "box", "class", "label_source")):
    with open(path, "w", encoding="utf-8") as fo:
        fo.write("\t".join(fields) + "\n")
        for r in rows:
            fo.write("\t".join(str(r.get(f, "")) for f in fields) + "\n")
