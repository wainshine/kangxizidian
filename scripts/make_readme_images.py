#!/usr/bin/env python3
"""make_readme_images.py — 生成 README/发布文档用的样张与「原书 vs 字体」对比图。

输出：
  docs/images/specimen.png      项目字体的多字号样张（配 OFL 参照字体字号标签）
  docs/images/book-vs-font.png  上：原书扫描裁片（同一页相邻字头）；下：当前字体渲染同一串字
  docs/images/method.png        （可选，文字流程条）

用法：
  .venv/bin/python scripts/make_readme_images.py --font work/font/build/KangXiKai-v2.6.2.ttf \
      --manifest work/font/build/manifest_v262.json --mapping work/lead/mapping_block_v271.jsonl
"""
import argparse, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))
from PIL import Image, ImageDraw, ImageFont

REF = os.path.join(ROOT, "work", "font", "_fonts", "LXGWWenKai-Regular.ttf")
OUT = os.path.join(ROOT, "docs", "images")

# 候选样张句（全为常用字；脚本会自动挑选字符全在字表中的句子）
CANDIDATES = [
    "天地玄黃 宇宙洪荒 日月盈昃 辰宿列張",
    "春眠不覺曉 處處聞啼鳥 夜來風雨聲",
    "大學之道 在明明德 在親民 在止於至善",
    "學而時習之 不亦說乎 有朋自遠方來",
    "永和九年 歲在癸丑 暮春之初 會于會稽",
    "山川之美 古來共談 高峰入雲 清流見底",
]


def load_chars(manifest):
    return set(json.load(open(manifest, encoding="utf-8"))["chars"])


def pick_phrase(chars):
    for s in CANDIDATES:
        body = s.replace(" ", "")
        if all(c in chars for c in body):
            return body
    # 兜底：从字表里挑 8 个常见字
    common = "永字八法天地玄黃宇宙洪荒日月星辰"
    ok = [c for c in common if c in chars]
    return " ".join("".join(ok[:8]))


def render_line(draw, text, font, xy, fill=0, anchor="la"):
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)


def draw_spaced(d, text, font, xy, gap=26, fill=0):
    x, y = xy
    for ch in text:
        if ch == " ":
            x += gap
            continue
        d.text((x, y), ch, font=font, fill=fill)
        x += d.textlength(ch, font=font) + gap
    return x


def pick_clean_phrase(font_path, chars):
    for cand in CANDIDATES:
        body = cand.replace(" ", "")
        if not all(c in chars for c in body):
            continue
        try:
            if any(_stray_score(font_path, c) > 0.0 for c in body):
                continue
        except Exception:
            continue
        return body
    # 兜底：从常用干净字里取 10 个
    out = []
    for c in "永字八法天地玄黃宇宙日月星辰書畫筆墨":
        if c in chars:
            try:
                if _stray_score(font_path, c) <= 0.0:
                    out.append(c)
            except Exception:
                pass
        if len(out) >= 10:
            break
    return "".join(out)


def make_specimen(font_path, chars, path):
    W, H = 1800, 1000
    im = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(im)
    f_title = ImageFont.truetype(font_path, 210)
    f_sub = ImageFont.truetype(font_path, 92)
    f_body = ImageFont.truetype(font_path, 92)
    f_small = ImageFont.truetype(font_path, 46)
    f_cap = ImageFont.truetype(REF, 26) if os.path.exists(REF) else ImageFont.load_default()
    phrase = pick_phrase(chars)  # 只要求字符齐全；样张优先好看、可读
    sub = "康熙五十五年刊本"
    sub2 = "楷書字頭"
    # 标题
    render_line(d, "康熙楷", f_title, (90, 40))
    d.text((W - 90, 120), "KangXi Kai", font=f_cap, fill=110, anchor="ra")
    # 副标题（只用字表内字符，避免出现缺字方块）
    x = draw_spaced(d, sub, f_sub, (96, 300), gap=18)
    d.text((x + 12, 330), "·", font=f_cap, fill=150)
    draw_spaced(d, sub2, f_sub, (x + 44, 300), gap=18)
    d.line([(90, 430), (W - 90, 430)], fill=200, width=2)
    # 主样张（自动选句；按可用宽度自适应字号/间距，避免出界）
    avail = W - 192
    for fsize, gap in ((92, 24), (84, 22), (76, 20), (68, 18)):
        f_try = ImageFont.truetype(font_path, fsize)
        wsum = sum(d.textlength(c, font=f_try) + gap for c in phrase) - gap
        if wsum <= avail:
            f_body = f_try
            draw_spaced(d, phrase, f_body, (96, 480), gap=gap)
            break
    # 小字号行
    for i, size in enumerate((46, 36, 28, 22)):
        f = ImageFont.truetype(font_path, size)
        draw_spaced(d, phrase, f, (96, 620 + i * 60), gap=6)
        d.text((W - 90, 620 + i * 60), f"{size}px", font=f_cap, fill=120, anchor="ra")
    d.line([(90, 900), (W - 90, 900)], fill=200, width=2)
    d.text((96, 925), "康熙五十五年内刊本《康熙字典》字头真迹 · headword-only · " + "17,005 real glyphs · OFL-1.1",
           font=f_cap, fill=120)
    im.save(path)
    print("saved", path)


def crop_from_page(page, box, pad=4):
    from review_sheet import page_gray
    g = page_gray(page, 150)
    bx = [int(round(v)) for v in box]
    x0, y0 = max(0, bx[0] - pad), max(0, bx[1] - pad)
    x1, y1 = min(g.shape[1], bx[2] + pad), min(g.shape[0], bx[3] + pad)
    import numpy as np
    return Image.fromarray(g[y0:y1, x0:x1]).convert("L")


def _stray_score(font_path, ch):
    import numpy as np, cv2
    from fidelity_eval import glyph_mask_from_font
    m = glyph_mask_from_font(font_path, ch)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    comps = [(int(st[i,0]), int(st[i,1]), int(st[i,2]), int(st[i,3]), int(st[i,4])) for i in range(1, n) if st[i,4] >= 12]
    if len(comps) <= 1:
        return 0.0
    main = max(comps, key=lambda c: c[4])
    mx0, my0, mw, mh = main[0] - 8, main[1] - 8, main[2] + 16, main[3] + 16
    stray = sum(c[4] for c in comps if c is not main
                and not (mx0 <= c[0] <= mx0 + mw and my0 <= c[1] <= my0 + mh)
                and c[4] >= 0.015 * sum(cc[4] for cc in comps))
    total = sum(c[4] for c in comps)
    return stray / max(1, total)


def make_glyph_grid(font_path, chars, path):
    curated = list("永字八法天地玄黃宇宙洪荒日月星辰金石書畫筆墨紙硯春夏秋冬東西南北"
                   "風雨雷電山河海岳雲霧雪霜松柏梅蘭竹菊琴棋詩酒茶香"
                   "仁義禮智信溫良恭儉讓中正和平上下左右見聞思學")
    sel = []
    for c in curated:
        if c not in chars or c in sel:
            continue
        try:
            if _stray_score(font_path, c) > 0.0:
                continue
        except Exception:
            continue
        sel.append(c)
        if len(sel) >= 48:
            break
    # 只展示常用/典雅的字，不用罕见字补齐（缺的格子就少几行）
    sel = sel[:36]  # 3 行 × 12 列，排满
    cols = 12
    rows = max(1, (len(sel) + cols - 1) // cols)
    cell = 150
    im = Image.new("L", (cols * cell, rows * cell), 255)
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(font_path, 118)
    for i, ch in enumerate(sel):
        r, c = divmod(i, cols)
        d.text((c * cell + cell // 2, r * cell + cell // 2 - 4), ch, font=f, fill=0, anchor="mm")
    for c in range(cols + 1):
        d.line([(c * cell, 0), (c * cell, rows * cell)], fill=225)
    for r in range(rows + 1):
        d.line([(0, r * cell), (cols * cell, r * cell)], fill=225)
    im.save(path)
    print("saved", path, len(sel))


def make_source_page(page, path):
    from review_sheet import page_gray
    g = page_gray(page, 150)
    h, w = g.shape[:2]
    half = g[:, w // 2:]          # 右半版（原书一页）
    im = Image.fromarray(half).convert("L")
    tw = 560
    im = im.resize((tw, int(im.height * tw / im.width)), Image.LANCZOS)
    im.save(path)
    print("saved", path, "page", page, im.size)


def make_book_vs_font(font_path, mapping_path, path, manifest_path):
    """上部=原书字头裁片（每字来自其实际页），下部=当前字体渲染同串字；只选已通过干净度检查的字。"""
    man = json.load(open(manifest_path, encoding="utf-8"))["chars"]
    # 候选：常用、结构有代表性；按顺序过滤出 8 个「字形干净（无游离碎片）」且字表内有的字
    curated = list("永字八法天地玄黃宇宙洪荒日月星辰楷書字頭點畫結構碑帖翰墨丹青")
    bad = set()
    for fn in ("work/lead/review-feedback-v262.json",):
        p = os.path.join(ROOT, fn)
        if os.path.exists(p):
            for x in json.load(open(p, encoding="utf-8")):
                bad.add(x.get("char"))
    for fn in ("work/lead/missing_scan_v262.jsonl", "work/lead/frame_scan_v262.jsonl"):
        p = os.path.join(ROOT, fn)
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                try:
                    bad.add(json.loads(line).get("char"))
                except Exception:
                    pass
    picked = []
    for ch in curated:
        if ch in picked or ch not in man or ch in bad:
            continue
        try:
            if _stray_score(font_path, ch) > 0.0:
                continue
        except Exception:
            continue
        picked.append(ch)
        if len(picked) == 8:
            break
    if len(picked) < 8:  # 兜底：任意干净字
        for ch in sorted(man):
            if ch in picked or ch in bad:
                continue
            try:
                if _stray_score(font_path, ch) <= 0.0:
                    picked.append(ch)
            except Exception:
                continue
            if len(picked) == 8:
                break
    items = [(ch, man[ch]["box"], man[ch]["page"]) for ch in picked]
    cell_w = 1180 // len(items)
    # 上：原书裁片并排（每字来自其实际页）
    src_strip = Image.new("L", (1180, 260), 245)
    for i, (ch, box, page) in enumerate(items):
        c = crop_from_page(page, box)
        c = c.resize((cell_w - 12, int(c.height * (cell_w - 12) / c.width)), Image.LANCZOS)
        src_strip.paste(c, (i * cell_w + 6, (260 - c.height) // 2))
    H = 300
    im = Image.new("L", (1180, 260 + H + 60), 255)
    im.paste(src_strip, (0, 0))
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(font_path, 200)
    for i, (ch, _, _) in enumerate(items):
        d.text((i * cell_w + cell_w // 2, 260 + H // 2 - 10), ch, font=f, fill=0, anchor="mm")
    cap = ImageFont.truetype(REF, 26) if os.path.exists(REF) else ImageFont.load_default()
    d.text((10, 265), "原书字头裁片（各字实际页/框）", font=cap, fill=110)
    d.text((10, 260 + H + 12), "KangXi Kai 渲染同串字头（%d 字）" % len(items), font=cap, fill=110)
    d.line([(0, 260), (1180, 260)], fill=210, width=2)
    im.save(path)
    print("saved", path, "chars", "".join(c for c, _, _ in items))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", default="work/font/build/KangXiKai-v2.6.2.ttf")
    ap.add_argument("--manifest", default="work/font/build/manifest_v262.json")
    ap.add_argument("--mapping", default="work/lead/mapping_block_v271.jsonl")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    font = os.path.join(ROOT, args.font)
    chars = load_chars(os.path.join(ROOT, args.manifest))
    make_specimen(font, chars, os.path.join(OUT, "specimen.png"))
    make_book_vs_font(font, os.path.join(ROOT, args.mapping),
                      os.path.join(OUT, "book-vs-font.png"),
                      os.path.join(ROOT, args.manifest))
    make_glyph_grid(font, chars, os.path.join(OUT, "glyphs-grid.png"))
    make_source_page("02_0029", os.path.join(OUT, "source-page.png"))


if __name__ == "__main__":
    main()
