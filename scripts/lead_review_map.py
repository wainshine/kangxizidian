#!/usr/bin/env python3
"""Lead · mapping 评审图：每页叠加「框 + 预测字」，供人工/LLM 目检。

用法：
  .venv/bin/python scripts/lead_review_map.py --mapping work/map/mapping.jsonl \
      --pages 01_0006,01_0007 --out work/lead/review_map
输出 <page>.png（半版并排，框上标预测字）与 <page>_crops.png（按阅读序裁框拼图）。
"""
import json, os, sys, argparse
import numpy as np
import cv2

cv2.setNumThreads(1)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw, ImageFont  # noqa: E402


def disp(ch):
    """PIL 可能缺字：扩展区显示为 〔僻〕。"""
    try:
        o = ord(ch)
        if o > 0xFFFF:
            return "〔" + ch + "〕"
    except Exception:
        pass
    return ch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping", required=True)
    ap.add_argument("--pages", default="")
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/review_map"))
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    import fitz
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))
    os.makedirs(args.out, exist_ok=True)
    want = set(args.pages.split(",")) if args.pages else None
    by_page = {}
    n_done = 0
    for line in open(args.mapping, encoding="utf-8"):
        r = json.loads(line)
        if want and r["page"] not in want:
            continue
        by_page.setdefault(r["page"], []).append(r)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Songti.ttc", 34)
    except Exception:
        font = ImageFont.load_default()
    for page, recs in sorted(by_page.items()):
        vol, pg = page[:2], int(page[3:])
        doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
        pix = doc[pg - 1].get_pixmap(dpi=args.dpi, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        doc.close()
        scale = args.dpi / 150.0
        vis = np.stack([img] * 3, axis=-1).astype(np.uint8)
        crops = []
        for rec in recs:
            for a in rec.get("assigned", []):
                ch = a["char"]
                box = [int(round(v * scale)) for v in a["cand"]["box"]]
                x0, y0, x1, y1 = box
                cv2.rectangle(vis, (x0, y0), (x1, y1), (0, 0, 255), 2)
                crops.append((ch, img[max(0, y0 - 10):y1 + 10, max(0, x0 - 10):x1 + 10]))
        im = Image.fromarray(vis)
        dr = ImageDraw.Draw(im)
        for rec in recs:
            for a in rec.get("assigned", []):
                box = [int(round(v * scale)) for v in a["cand"]["box"]]
                dr.text((box[0], max(0, box[1] - 38)), disp(a["char"]), font=font, fill=(255, 0, 0))
        dr.text((10, 10), page, font=font, fill=(0, 0, 255))
        im.resize((im.width // 3, im.height // 3)).save(os.path.join(args.out, f"{page}.png"))
        # crops montage
        if crops:
            cw = max(c.shape[1] for _, c in crops) + 12
            chh = max(c.shape[0] for _, c in crops) + 46
            cols = min(10, len(crops))
            rows = (len(crops) + cols - 1) // cols
            S = Image.new("RGB", (cols * cw, rows * chh), (255, 255, 255))
            sd = ImageDraw.Draw(S)
            for k, (ch, c) in enumerate(crops):
                x, y = (k % cols) * cw, (k // cols) * chh
                S.paste(Image.fromarray(np.stack([c] * 3, -1)), (x + 6, y + 40))
                sd.text((x + 6, y + 4), disp(ch), font=font, fill=(0, 0, 0))
            S.save(os.path.join(args.out, f"{page}_crops.png"))
        n_done += 1
        if args.limit and n_done >= args.limit:
            break
    print("pages", n_done, "->", args.out)


if __name__ == "__main__":
    main()
