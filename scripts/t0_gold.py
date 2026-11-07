#!/usr/bin/env python3
"""T0 · 50 框金标准制作

流程：检测提议框（150dpi）→ 算法紧化（提议框邻域内、与中心连通的墨迹 bbox）
→ 输出目检拼图（每框一个格子，画出紧化框）→ 人工逐框 accept/reject（下一步脚本）
→ gold json + IoU 基线。

本脚本只做：提议收集 + 紧化 + 拼图。
"""
import json, os
import numpy as np
import cv2

cv2.setNumThreads(1)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T00 = os.path.join(ROOT, "work", "t00")

PAGES = {"01_0006": 3, "01_0110": 14, "13_0163": 34, "08_0020": 8}   # 目标 ~59 提议 → 金标 ~50


def ink_of(gray150):
    ink = (gray150 <= 150).astype(np.uint8)
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 200))
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (200, 1))
    v = cv2.morphologyEx(ink, cv2.MORPH_OPEN, vk)
    h = cv2.morphologyEx(ink, cv2.MORPH_OPEN, hk)
    return cv2.subtract(cv2.subtract(ink, v), h)


def refine(ink, box):
    """紧化：提议框 pad 20% 邻域内，取与中心区域重叠的连通域并集 bbox"""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    px, py = int(w * 0.2), int(h * 0.2)
    X0, Y0 = max(0, x0 - px), max(0, y0 - py)
    X1, Y1 = x1 + px, y1 + py
    sub = ink[Y0:Y1, X0:X1]
    n, lab, stats, _ = cv2.connectedComponentsWithStats(sub, connectivity=8)
    cx, cy = (x0 + x1) / 2 - X0, (y0 + y1) / 2 - Y0
    keep = np.zeros_like(sub, dtype=bool)
    for i in range(1, n):
        sx, sy, sw, sh, area = stats[i]
        if area < 30:
            continue
        # 与中心 60% 区域重叠才算本字
        ox = max(0, min(cx + w * 0.3, sx + sw) - max(cx - w * 0.3, sx))
        oy = max(0, min(cy + h * 0.3, sy + sh) - max(cy - h * 0.3, sy))
        if ox > 0 and oy > 0:
            keep |= (lab == i)
    ys, xs = np.where(keep)
    if len(xs) == 0:
        return None
    return (X0 + int(xs.min()), Y0 + int(ys.min()),
            X0 + int(xs.max()) + 1, Y0 + int(ys.max()) + 1)


def main():
    heads = [json.loads(l) for l in open(os.path.join(T00, "headwords.jsonl"), encoding="utf-8")]
    by_page = {}
    for r in heads:
        key = f"{r['pdf']}_{r['page']:04d}"
        by_page.setdefault(key, []).append(r)

    gold = []
    for key, quota in PAGES.items():
        props = by_page.get(key, [])[:quota]
        gray = cv2.imread(os.path.join(T00, "pages", key + ".png"), cv2.IMREAD_GRAYSCALE)
        ink = ink_of(gray)
        for i, p in enumerate(props):
            box = (p["x0"], p["y0"], p["x1"], p["y1"])
            rb = refine(ink, box)
            gold.append({"page": key, "idx": i, "proposal": list(box),
                         "refined": list(rb) if rb else None,
                         "crop": f"crops/{key}_{p['side']}_{i:03d}.png"})
    json.dump(gold, open(os.path.join(T00, "gold_candidates.json"), "w"),
              ensure_ascii=False, indent=1)

    # 拼图：每格画出紧化框（绿）供人工核验
    from PIL import Image, ImageDraw
    CELL = 260
    COLS = 8
    rows = (len(gold) + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * CELL, rows * (CELL + 22)), "white")
    d = ImageDraw.Draw(sheet)
    for i, g in enumerate(gold):
        gx = cv2.imread(os.path.join(T00, "pages", g["page"] + ".png"), cv2.IMREAD_GRAYSCALE)
        if gx is None:
            continue
        rx0, ry0, rx1, ry1 = g["refined"] if g["refined"] else g["proposal"]
        view_pad = 20
        vx0, vy0 = max(0, rx0 - view_pad), max(0, ry0 - view_pad)
        vx1, vy1 = min(gx.shape[1], rx1 + view_pad), min(gx.shape[0], ry1 + view_pad)
        vis = cv2.cvtColor(gx[vy0:vy1, vx0:vx1], cv2.COLOR_GRAY2RGB)
        # 画金框（绿）
        cv2.rectangle(vis, (rx0 - vx0, ry0 - vy0), (rx1 - vx0, ry1 - vy0), (0, 200, 0), 2)
        im = Image.fromarray(vis)
        im.thumbnail((CELL - 8, CELL - 18))
        x = (i % COLS) * CELL
        y = (i // COLS) * (CELL + 22)
        sheet.paste(im, (x + 4, y + 4))
        d.text((x + 4, y + CELL - 8), f"{g['page']} #{i}", fill="blue")
    out = os.path.join(T00, "gold_sheet.png")
    sheet.save(out)
    print(out, sheet.size, "candidates:", len(gold))


if __name__ == "__main__":
    main()
