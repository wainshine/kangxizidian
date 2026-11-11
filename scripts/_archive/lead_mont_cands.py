#!/usr/bin/env python3
"""Lead · 候选裁框拼图（复核 detector 候选/分类用）。
对每页：把 R/L 半版候选（可选过滤）裁出来按阅读序编号拼图，标注 hw 分/sr/argmax。
用法: .venv/bin/python scripts/lead_mont_cands.py --pages 01_0060,01_0085 --out work/lead/mont2
"""
import json, os, sys, argparse
import numpy as np, cv2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True)
    ap.add_argument("--boxes", default=os.path.join(ROOT, "work/lead/boxes300"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/mont2"))
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--min-hw", type=float, default=0.35)
    ap.add_argument("--min-sr", type=float, default=1.3)
    ap.add_argument("--max-sr", type=float, default=3.2)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    import fitz
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))
    try:
        fnt = ImageFont.truetype("/System/Library/Fonts/Supplemental/Songti.ttc", 18)
    except Exception:
        fnt = ImageFont.load_default()
    for page in args.pages.split(","):
        vol, pg = page[:2], int(page[3:])
        r = json.load(open(os.path.join(args.boxes, f"{page}.json"), encoding="utf-8"))
        doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
        pix = doc[pg - 1].get_pixmap(dpi=args.dpi, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        doc.close()
        crops = []
        for half in ("R", "L"):
            cands = r["halves"][half]["cands"]
            for i, c in enumerate(cands):
                hw = c["cls"].get("headword", 0)
                sr = c.get("size_ratio", 0)
                if hw < args.min_hw or not (args.min_sr <= sr <= args.max_sr):
                    continue
                x0, y0, x1, y1 = [v * 2 for v in c["box"]]
                pad = 14
                crop = img[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]
                if crop.size == 0:
                    continue
                crops.append((half, i, c, crop))
        if not crops:
            print(page, "no crops")
            continue
        cw = max(c.shape[1] for *_, c in crops) + 14
        ch = max(c.shape[0] for *_, c in crops) + 52
        cols = 8
        rows = (len(crops) + cols - 1) // cols
        S = Image.new("RGB", (cols * cw, rows * ch), (255, 255, 255))
        dr = ImageDraw.Draw(S)
        for k, (half, i, c, crop) in enumerate(crops):
            x, y = (k % cols) * cw, (k // cols) * ch
            S.paste(Image.fromarray(np.stack([crop] * 3, -1)), (x + 7, y + 34))
            hw = c["cls"].get("headword", 0)
            dr.text((x + 6, y + 4), f"{half}{i} hw={hw:.2f}", font=fnt, fill=(0, 0, 0))
            dr.text((x + 6, y + 18), f"sr={c.get('size_ratio', 0):.2f} {c['argmax']}",
                    font=fnt, fill=(0, 0, 200))
        S.save(os.path.join(args.out, f"{page}_cands.png"))
        print(page, len(crops), "->", os.path.join(args.out, f"{page}_cands.png"))

if __name__ == "__main__":
    main()
