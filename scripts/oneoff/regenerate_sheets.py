#!/usr/bin/env python3
"""按发布时的确定参数重生成 specimen / random120 原图（用于比对 owner 标记）。"""
import json, os, random, sys
from PIL import Image, ImageDraw, ImageFont
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

VER = {
    "2.4.11": {"man": "work/lead/manifest-v2411.json", "font": "release/KangXiKai-v2.4.11/KangXiKai-Regular-v2.4.11.ttf"},
    "2.4.13": {"man": "work/font/build/release_extras/manifest-v2413.json", "font": "release/KangXiKai-v2.4.13/KangXiKai-Regular-v2.4.13.ttf"},
    "2.4.14": {"man": "work/font/build/release_extras/manifest-v2414.json", "font": "release/KangXiKai-v2.4.14/KangXiKai-Regular-v2.4.14.ttf"},
}


def gen(ver, outdir):
    cfg = VER[ver]
    man = json.load(open(os.path.join(ROOT, cfg["man"]), encoding="utf-8"))["chars"]
    chars = sorted(man)
    font = os.path.join(ROOT, cfg["font"])
    # specimen: 12x5, font 84, seed 202
    random.seed(202); sample = random.sample(chars, min(60, len(chars)))
    f = ImageFont.truetype(font, 84)
    S = Image.new("L", (12 * 100, 5 * 112), 255); d = ImageDraw.Draw(S)
    for i, ch in enumerate(sample):
        d.text(((i % 12) * 100 + 2, (i // 12) * 112 + 2), ch, font=f, fill=0)
    S.save(os.path.join(ROOT, outdir, f"specimen-{ver}.png"))
    # random120: 12x10, font 70, seed 9
    random.seed(9); rnd = random.sample(chars, min(120, len(chars)))
    f2 = ImageFont.truetype(font, 70)
    S2 = Image.new("L", (12 * 90, 10 * 100), 255); d2 = ImageDraw.Draw(S2)
    for i, ch in enumerate(rnd):
        d2.text(((i % 12) * 90 + 2, (i // 12) * 100 + 2), ch, font=f2, fill=0)
    S2.save(os.path.join(ROOT, outdir, f"random120-{ver}.png"))
    print(ver, "sheets regenerated")


if __name__ == "__main__":
    os.makedirs(os.path.join(ROOT, "work/review/regen"), exist_ok=True)
    for v in ("2.4.11", "2.4.13", "2.4.14"):
        gen(v, "work/review/regen")
