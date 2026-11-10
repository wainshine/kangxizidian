#!/usr/bin/env python3
"""v2.4.6 局部精修切框：以现有近似框为起点，在源扫描上做「局部墨迹群紧化」。

对每个 (page, box)：
  1) 300dpi 渲染该页一次；
  2) 取 box 外扩 0.4*h0 的局部窗口，flatten + Sauvola 二值；
  3) 组件聚类：以与 box 重叠最大的组件为种子，并入与其间距<=6px@150 的组件；
  4) 扁平横画（二/三）合并；输出 tight 墨迹 bbox（不越出窗口）；
  5) 与旧框比较：偏移/面积比 → 记录 changed。
输出 work/lead/refined_boxes_v246.jsonl（page/half/char/old/new/...）
"""
import json, os, sys
import numpy as np, cv2, fitz
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def flatten_sauvola(g, w=25, k=0.22):
    g32 = g.astype(np.float32)
    m = cv2.boxFilter(g32, -1, (w, w))
    m2 = cv2.boxFilter(g32 * g32, -1, (w, w))
    s = np.sqrt(np.maximum(m2 - m * m, 0))
    T = m * (1 + k * (s / 128.0 - 1))
    return (g32 < T).astype(np.uint8)


def refine_one(ink, box150, h0=37.0):
    """ink: 300dpi 二值图；box150: 150dpi 坐标框。返回新 150dpi 框或 None。"""
    B = 2  # 300dpi/150dpi
    x0, y0, x1, y1 = [int(v) * B for v in box150]
    pad = int(0.45 * h0 * B)
    H, W = ink.shape
    wx0, wy0 = max(0, x0 - pad), max(0, y0 - pad)
    wx1, wy1 = min(W, x1 + pad), min(H, y1 + pad)
    win = ink[wy0:wy1, wx0:wx1]
    if win.size == 0:
        return None
    n, lab, st, _ = cv2.connectedComponentsWithStats(win, 8)
    if n <= 1:
        return None
    # 旧框在窗口内坐标
    bx0, by0, bx1, by1 = x0 - wx0, y0 - wy0, x1 - wx0, y1 - wy0
    boxes = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a < 30:
            continue
        boxes.append([i, int(x), int(y), int(w), int(h), int(a)])
    if not boxes:
        return None
    # 与旧框的交叠面积
    def ov(b):
        _, x, y, w, h, a = b
        ox = max(0, min(x + w, bx1) - max(x, bx0))
        oy = max(0, min(y + h, by1) - max(y, by0))
        return ox * oy
    seed = max(boxes, key=ov)
    if ov(seed) == 0:
        # 旧框内无墨迹组件（框偏移很大）：取离框中心最近的
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        seed = min(boxes, key=lambda b: (b[1] + b[3] / 2 - cx) ** 2 + (b[2] + b[4] / 2 - cy) ** 2)
    sel = {seed[0]}
    changed = True
    gap = 6 * B
    while changed:
        changed = False
        cur = [b for b in boxes if b[0] in sel]
        x0c = min(b[1] for b in cur); y0c = min(b[2] for b in cur)
        x1c = max(b[1] + b[3] for b in cur); y1c = max(b[2] + b[4] for b in cur)
        for b in boxes:
            if b[0] in sel:
                continue
            _, x, y, w, h, a = b
            if x + w + gap < x0c or x0c + (x1c - x0c) + gap < x:
                continue
            if y + h + gap < y0c or y0c + (y1c - y0c) + gap < y:
                continue
            dx = max(0, max(x0c, x) - min(x1c, x + w))
            dy = max(0, max(y0c, y) - min(y1c, y + h))
            if dx * dx + dy * dy <= gap * gap:
                # 尺寸约束：合并后不超过 3*h0
                nw = max(x1c, x + w) - min(x0c, x); nh = max(y1c, y + h) - min(y0c, y)
                if nw <= 3.2 * h0 * B and nh <= 3.2 * h0 * B:
                    sel.add(b[0]); changed = True
    cur = [b for b in boxes if b[0] in sel]
    nx0 = min(b[1] for b in cur); ny0 = min(b[2] for b in cur)
    nx1 = max(b[1] + b[3] for b in cur); ny1 = max(b[2] + b[4] for b in cur)
    nx0 += wx0; ny0 += wy0; nx1 += wx0; ny1 += wy0
    return [int(round(nx0 / B)), int(round(ny0 / B)), int(round(nx1 / B)), int(round(ny1 / B))]


def job(pages_boxes):
    vol, page, items = pages_boxes
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
    pix = doc[int(page) - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
    g = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    doc.close()
    ink = flatten_sauvola(g)
    out = []
    for it in items:
        nb = refine_one(ink, it["box"])
        out.append({**it, "new": nb})
    return out


def main():
    ap = __import__("argparse").ArgumentParser()
    ap.add_argument("--boxes", default=os.path.join(ROOT, "work/lead/manifest-v245.json"))
    ap.add_argument("--limit", type=int, default=0, help="只做前 N 个（调试）")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/refined_boxes_v246.jsonl"))
    args = ap.parse_args()
    man = json.load(open(args.boxes, encoding="utf-8"))
    chars = man["chars"] if "chars" in man else man
    bypage = {}
    for ch, r in chars.items():
        key = (r["page"][:2], r["page"][3:])
        bypage.setdefault(key, []).append({"char": ch, "page": r["page"], "half": r.get("half", "R"),
                                           "box": list(r["box"])})
    jobs = [(k[0], k[1], v) for k, v in bypage.items()]
    if args.limit:
        # 只取前 N 个字
        flat = [it for _, _, v in jobs for it in v][: args.limit]
        bypage = {}
        for it in flat:
            key = (it["page"][:2], it["page"][3:])
            bypage.setdefault(key, []).append(it)
        jobs = [(k[0], k[1], v) for k, v in bypage.items()]
    print("pages", len(jobs), "boxes", sum(len(v) for _, _, v in jobs), flush=True)
    done = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex, open(args.out, "w", encoding="utf-8") as fo:
        for rows in ex.map(job, jobs, chunksize=4):
            for r in rows:
                fo.write(json.dumps(r, ensure_ascii=False) + "\n")
            done += 1
            if done % 200 == 0:
                print("pages", done, flush=True)
    print("finished", done, args.out, flush=True)


if __name__ == "__main__":
    main()
