#!/usr/bin/env python3
"""锚点对比图：owner 11 + demo 28 金标框 vs 当前字体使用的框，逐字对比。

每格：原书裁片（画两框：绿=金标锚点框，蓝=当前字体框）+ 当前字体字形 + 坐标/偏移/IoU。
输出 work/review/anchors-compare.png + .json
"""
import json, os, sys
import numpy as np, fitz
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(ROOT, "release/KangXiKai-v2.4.15/KangXiKai-Regular-v2.4.15.ttf")
MAN = json.load(open(os.path.join(ROOT, "work/lead/manifest-v2415.json"), encoding="utf-8"))["chars"]
MP = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))


def iou(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1]); ub = (b[2] - b[0]) * (b[3] - b[1])
    return inter / max(1, ua + ub - inter)


def page_gray(page):
    vol = page[:2]; pno = int(page[3:])
    doc = fitz.open(os.path.join(ROOT, "康熙字典", MP[vol]))
    pix = doc[pno - 1].get_pixmap(dpi=150, colorspace=fitz.csGRAY)
    g = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    doc.close()
    return g


def glyph_img(ch, size=140):
    f = ImageFont.truetype(FONT, int(size * 0.8))
    im = Image.new("L", (size, size), 255)
    ImageDraw.Draw(im).text((size // 2, int(size * 0.92)), ch, fill=0, font=f, anchor="ms")
    return im


def crop_with_boxes(g, anchor_box, cur_box, size=190):
    ax0, ay0, ax1, ay1 = anchor_box
    w = max(80, ax1 - ax0); h = max(80, ay1 - ay0)
    pad = int(0.9 * max(w, h))
    x0 = max(0, min(ax0 - pad, ax0 - 20)); y0 = max(0, min(ay0 - pad, ay0 - 20))
    x1 = min(g.shape[1], ax1 + pad); y1 = min(g.shape[0], ay1 + pad)
    sub = Image.fromarray(g[y0:y1, x0:x1]).convert("RGB")
    sub = sub.resize((size, size))
    sx = size / max(1, (x1 - x0)); sy = size / max(1, (y1 - y0))
    d = ImageDraw.Draw(sub)
    def r(b, color):
        d.rectangle([int((b[0] - x0) * sx), int((b[1] - y0) * sy),
                     int((b[2] - x0) * sx), int((b[3] - y0) * sy)], outline=color, width=2)
    r(anchor_box, (0, 160, 0))
    if cur_box:
        r(cur_box, (0, 90, 220))
    return sub


def main():
    anchors = []
    for e in json.load(open(os.path.join(ROOT, "work/font/owner_verified_boxes.json"), encoding="utf-8")):
        anchors.append({"set": "owner", "char": e["char"], "page": e["page"],
                        "half": e.get("half"), "box": e["box"]})
    for line in open(os.path.join(ROOT, "work/font/demo/manifest.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        anchors.append({"set": "demo", "char": r["char"], "page": r["page"],
                        "half": r.get("half"), "box": r["box"]})
    cache = {}
    rows = []
    for a in anchors:
        g = cache.get(a["page"])
        if g is None:
            g = page_gray(a["page"]); cache[a["page"]] = g
        cur = MAN.get(a["char"])
        cur_box = cur["box"] if cur and cur["page"] == a["page"] else None
        io = round(iou(a["box"], cur_box), 3) if cur_box else None
        dx = dy = None
        if cur_box:
            dx = int((cur_box[0] + cur_box[2]) / 2 - (a["box"][0] + a["box"][2]) / 2)
            dy = int((cur_box[1] + cur_box[3]) / 2 - (a["box"][1] + a["box"][3]) / 2)
        rows.append({**a, "current_box": cur_box, "iou": io, "dx": dx, "dy": dy,
                     "img": crop_with_boxes(g, a["box"], cur_box),
                     "glyph": glyph_img(a["char"])})
    # 拼图：每行 5 个
    cols = 5
    cw, chh = 300, 400
    S = Image.new("RGB", (cols * cw, ((len(rows) + cols - 1) // cols) * chh), (255, 255, 255))
    d = ImageDraw.Draw(S)
    fnt = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 13)
    fch = ImageFont.truetype(FONT, 22)
    for i, r in enumerate(rows):
        x = (i % cols) * cw; y = (i // cols) * chh
        S.paste(r["img"], (x + 55, y + 4))
        S.paste(r["glyph"], (x + 80, y + 200))
        d.text((x + 4, y + 202), r["char"], font=fch, fill=(0, 0, 0))
        d.text((x + 4, y + 232), f'{r["set"]} {r["page"]} {r["half"]}', font=fnt, fill=(0, 0, 0))
        d.text((x + 4, y + 248), f'anchor={r["box"]}', font=fnt, fill=(0, 120, 0))
        d.text((x + 4, y + 264), f'cur={r["current_box"]}', font=fnt, fill=(0, 70, 200))
        d.text((x + 4, y + 280), f'IoU={r["iou"]} dx={r["dx"]} dy={r["dy"]}', font=fnt, fill=(0, 0, 0))
    out_png = os.path.join(ROOT, "work/review/anchors-compare.png")
    S.save(out_png)
    slim = [{k: v for k, v in r.items() if k not in ("img", "glyph")} for r in rows]
    json.dump(slim, open(os.path.join(ROOT, "work/review/anchors-compare.json"), "w"),
              ensure_ascii=False, indent=1)
    print(json.dumps({"n": len(rows), "png": out_png,
                      "iou_mean": round(float(np.mean([r["iou"] for r in rows if r["iou"] is not None])), 3),
                      "iou_ge_09": sum(1 for r in rows if r["iou"] is not None and r["iou"] >= 0.9),
                      "missing_in_font": sum(1 for r in rows if r["iou"] is None)}))


if __name__ == "__main__":
    main()
