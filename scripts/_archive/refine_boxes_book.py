#!/usr/bin/env python3
"""全量局部精修切框（150dpi，按页并行）：
对每个现有框，取外扩窗口 → Sauvola 二值 → 选「全内或中心在内」的组件 → tight 墨迹 bbox。
输出 work/lead/refined_boxes_v246.jsonl，并统计变更。
"""
import json, os, sys
import numpy as np, cv2, fitz
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def flatten(g, w=25, k=0.22):
    g32 = g.astype(np.float32)
    m = cv2.boxFilter(g32, -1, (w, w))
    m2 = cv2.boxFilter(g32 * g32, -1, (w, w))
    s = np.sqrt(np.maximum(m2 - m * m, 0))
    T = m * (1 + k * (s / 128.0 - 1))
    return (g32 < T).astype(np.uint8)


def refine(ink, box, h0=37.0, tol=8):
    x0, y0, x1, y1 = [int(v) for v in box]
    pad = int(0.5 * h0)
    H, W = ink.shape
    wx0, wy0 = max(0, x0 - pad), max(0, y0 - pad)
    wx1, wy1 = min(W, x1 + pad), min(H, y1 + pad)
    win = ink[wy0:wy1, wx0:wx1]
    n, lab, st, _ = cv2.connectedComponentsWithStats(win, 8)
    bx0, by0, bx1, by1 = x0 - wx0, y0 - wy0, x1 - wx0, y1 - wy0
    barea = max(1, (bx1 - bx0) * (by1 - by0))
    sel = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a < 20:
            continue
        # 只收「完全在旧框内」的组件（容差 8px）：
        # 不允许向外扩张，避免把右侧注文/框线残片纳入（路 类边角料）
        fully = x >= bx0 - tol and y >= by0 - tol and x + w <= bx1 + tol and y + h <= by1 + tol
        if fully:
            sel.append((x, y, w, h))
    if not sel:
        return None
    nx0 = min(s[0] for s in sel); ny0 = min(s[1] for s in sel)
    nx1 = max(s[0] + s[2] for s in sel); ny1 = max(s[1] + s[3] for s in sel)
    return [int(nx0 + wx0), int(ny0 + wy0), int(nx1 + wx0), int(ny1 + wy0)]


def job(args):
    vol, page, items = args
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
    pix = doc[int(page) - 1].get_pixmap(dpi=150, colorspace=fitz.csGRAY)
    g = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    doc.close()
    ink = flatten(g)
    out = []
    for it in items:
        nb = refine(ink, it["box"])
        out.append({**it, "new": nb})
    return out


def main():
    man = json.load(open(os.path.join(ROOT, "work/lead/manifest-v245.json"), encoding="utf-8"))
    chars = man["chars"]
    bypage = {}
    for ch, r in chars.items():
        bypage.setdefault((r["page"][:2], r["page"][3:]), []).append(
            {"char": ch, "page": r["page"], "half": r.get("half", "R"), "box": list(r["box"]),
             "label_source": r.get("label_source", "")})
    jobs = [(k[0], k[1], v) for k, v in bypage.items()]
    print("pages", len(jobs), "chars", len(chars), flush=True)
    out_path = os.path.join(ROOT, "work/lead/refined_boxes_v246.jsonl")
    done = 0
    with ProcessPoolExecutor(max_workers=8) as ex, open(out_path, "w", encoding="utf-8") as fo:
        for rows in ex.map(job, jobs, chunksize=4):
            for r in rows:
                fo.write(json.dumps(r, ensure_ascii=False) + "\n")
            done += 1
            if done % 500 == 0:
                print("pages", done, flush=True)
    print("finished", done, out_path, flush=True)


if __name__ == "__main__":
    main()
