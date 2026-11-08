#!/usr/bin/env python3
"""C 流 · 样张：用构建出的 TTF 渲染全部 demo 字（96px / 48px 各一行网格）。

用法：
  .venv/bin/python scripts/font_specimen.py \
      --font work/font/demo/KangXiKai-demo-v0.1.0.ttf --out work/font/demo/specimen.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work" / "font"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", default=str(WORK / "demo" / "KangXiKai-demo-v0.1.0.ttf"))
    ap.add_argument("--manifest", default=str(WORK / "demo" / "manifest.json"))
    ap.add_argument("--out", default=str(WORK / "demo" / "specimen.png"))
    ap.add_argument("--big", type=int, default=96)
    ap.add_argument("--small", type=int, default=48)
    ap.add_argument("--cols", type=int, default=20)
    args = ap.parse_args()

    chars = sorted(json.load(open(args.manifest))["chars"])
    font = ImageFont.truetype(args.font, args.big)
    font_s = ImageFont.truetype(args.font, args.small)
    try:
        label_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Songti.ttc",
                                        16, index=7)
    except Exception:
        label_font = ImageFont.load_default()

    cols = args.cols
    cell_w = args.big + 26
    cell_h = args.big + 34
    rows_big = (len(chars) + cols - 1) // cols
    # 小字号行：每行 48px 字，一行 40 字
    small_cols = max(cols * 2, 40)
    rows_small = (len(chars) + small_cols - 1) // small_cols

    margin = 34
    W = max(cols * cell_w, small_cols * (args.small + 10)) + margin * 2
    H = margin + 58 + rows_big * cell_h + 46 + rows_small * (args.small + 14) + 70
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    title = (f"KangXi Kai  Regular  v0.1.0 demo — {len(chars)} real headword glyphs  "
             f"(extracted from 1716 Kangxi Dictionary woodblock scans)")
    d.text((margin, 12), title, fill="black", font=label_font)
    d.text((margin, 32), f"{args.big}px / {args.small}px — rendered with the font itself",
           fill=(90, 90, 90), font=label_font)

    y0 = margin + 58
    for i, ch in enumerate(chars):
        x = margin + (i % cols) * cell_w
        y = y0 + (i // cols) * cell_h
        d.text((x + 8, y), ch, fill="black", font=font)
        d.text((x + 8, y + args.big + 10), f"{ch} U+{ord(ch):04X}", fill=(120, 120, 120),
               font=label_font)

    y1 = y0 + rows_big * cell_h + 36
    d.text((margin, y1 - 26), f"{args.small}px line — 全部 demo 字", fill=(60, 60, 60),
           font=label_font)
    for i, ch in enumerate(chars):
        x = margin + (i % small_cols) * (args.small + 10)
        y = y1 + (i // small_cols) * (args.small + 14)
        d.text((x, y), ch, fill="black", font=font_s)

    footer = ("source: data/gold-certified/gold50.json (owner-certified 60 boxes) + "
              "t2 review-sample boxes; label: font:目检; licence: SIL OFL 1.1")
    d.text((margin, H - 24), footer, fill=(120, 120, 120), font=label_font)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    print("specimen:", out, im.size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
