#!/usr/bin/env python3
"""T0.0 · OCR 质检拼图：随机抽 N 个字头裁剪 + 识别结果拼成 contact sheet 供目检"""
import json, os, random, sys
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T00 = os.path.join(ROOT, "work", "t00")


def main(n=60, seed=7):
    recs = [json.loads(l) for l in open(os.path.join(T00, "ocr.jsonl"), encoding="utf-8")]
    random.seed(seed)
    pick = random.sample(recs, min(n, len(recs)))
    cell = 120
    cols = 10
    rows = (len(pick) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 22)), "white")
    dr = ImageDraw.Draw(sheet)
    for i, r in enumerate(pick):
        p = os.path.join(T00, r["crop"])
        im = Image.open(p).convert("L")
        im.thumbnail((cell - 8, cell - 8))
        x = (i % cols) * cell
        y = (i // cols) * (cell + 22)
        sheet.paste(im, (x + 4, y + 2))
        dr.text((x + 4, y + cell), f"{r['text']} {r['conf']:.2f}", fill="red")
    out = os.path.join(T00, "ocr_qc_sheet.png")
    sheet.save(out)
    print(out, sheet.size)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 60,
         int(sys.argv[2]) if len(sys.argv) > 2 else 7)
