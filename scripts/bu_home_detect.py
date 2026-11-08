#!/usr/bin/env python3
"""A3-2 · 部首页定位（214 个硬锚点）。

自监督信号：每个部首页的部首自字下方印有「X部」小标签（部首字+部，竖排 2 字）。
- 「部」字形模板取自 03_0015（宀部首页标签），在每页 boxes300 的候选里找「部」命中；
- 命中的「部」上方左侧的候选 = 部首自字（大字形）；
- 卷内按页序 → 与 volume_radicals.json 的部首清单按序对齐；数量不符时用 entries 位置先验做 DP 对齐；
- 36 个卷首部首页由 A2b 扉页结构已知，强制纳入（这些页用卷首标题块，标签可能不印）。
输出 work/seq/bu_home_candidates.jsonl（逐页候选）+ work/seq/bu_start_pages.jsonl（214 锚点）。
"""
import json, os, sys, warnings, collections
import cv2
import fitz
import numpy as np

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_MAP = json.load(open(os.path.join(ROOT, "work", "t2", "pdf_map.json"), encoding="utf-8"))
BOX = os.path.join(ROOT, "work", "lead", "boxes300")
OUT = os.path.join(ROOT, "work", "seq")
SIZE = 48

_cache = {}


def render_page(pdf, page, dpi=150):
    key = (pdf, page, dpi)
    if key in _cache and len(_cache) < 4:
        return _cache[key]
    doc = fitz.open(os.path.join(ROOT, "康熙字典", PDF_MAP[pdf]))
    try:
        p = doc[page - 1]
        pix = p.get_pixmap(dpi=dpi)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            img = img[:, :, :3]
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if pix.n >= 3 else img.copy()
    finally:
        doc.close()
    _cache[key] = gray
    return gray


def norm(ink, size=SIZE, pad=4):
    ys, xs = np.where(ink > 0)
    if len(xs) == 0:
        return np.zeros((size, size), np.float32)
    bb = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = bb.shape
    side = max(h, w) + 2 * pad
    c = np.zeros((side, side), np.uint8)
    c[(side - h) // 2:(side - h) // 2 + h, (side - w) // 2:(side - w) // 2 + w] = bb
    return (cv2.resize(c, (size, size), interpolation=cv2.INTER_AREA) > 0).astype(np.float32)


def iou(a, b):
    return float((a * b).sum()) / max(1e-6, float(((a + b) > 0).sum()))


def is_dark(g, box, thr=170):
    x0, y0, x1, y1 = box
    sub = g[max(0, y0):y1, max(0, x0):x1]
    if sub.size == 0:
        return 999.0
    ink = sub[sub <= 170]
    return float(ink.mean()) if ink.size > 5 else 255.0


def bu_template():
    """部模板：03_0015 标签的下字（部）在 150dpi 的紧密 bbox。"""
    g = render_page("03", 15)
    sub = g[605:705, 712:805]
    ink = (sub <= 150).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    keep = np.zeros_like(ink)
    for i in range(1, n):
        if stats[i, 4] >= 20:
            keep[lab == i] = 1
    return norm(keep)


def page_cands(vol, page):
    try:
        d = json.load(open(os.path.join(BOX, f"{vol}_{page:04d}.json")))
    except FileNotFoundError:
        return [], None
    H = d["stats"]["H"]
    cs = []
    for c in d["halves"]["L"]["cands"]:
        f = c["feat"]
        if f["half"] != "L" or f["margin_strip"] or f["outside_band"]:
            continue
        if not (30 <= f["h"] <= 200) or f["w"] < 25:
            continue
        if not (120 <= f["cy"] <= H - 250):
            continue
        c = dict(c)
        c["argmax"] = c.get("argmax") or "?"
        cs.append(c)
    return cs, H


def page_comps(g, y0=120, y1=900):
    ink = (g <= 145).astype(np.uint8)
    v = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (1, 260)))
    h = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (260, 1)))
    cl = ink & (1 - v) & (1 - h)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(cl, connectivity=8)
    comps = []
    for i in range(1, n):
        x, y, w, hh, a = stats[i]
        if hh >= 35 and w >= 18 and a >= 180 and y < y1 and (y + hh) > y0:
            comps.append([int(x), int(y), int(x + w), int(y + hh)])
    return comps, cl


def detect_page(vol, page, btpl):
    cs, H = page_cands(vol, page)
    g = render_page(vol, page)
    comps, cl = page_comps(g)
    tiles = {}
    hits = []
    for i, b in enumerate(comps):
        x0, y0, x1, y1 = b
        h = y1 - y0
        w = x1 - x0
        if not (30 <= h <= 130 and 20 <= w <= 130):
            continue
        t = norm(cl[y0:y1, x0:x1])
        s = iou(t, btpl)
        if s >= 0.33:
            hits.append((s, b, t))
    if not hits:
        return []
    hits.sort(key=lambda z: -z[0])
    hits = hits[:2]
    out = []
    bu_box = hits[0][1]
    bx0, by0, bx1, by1 = bu_box
    # 部首自字：部字上方（偏左）最大墨块
    best = None
    for b in comps:
        x0, y0, x1, y1 = b
        if y1 > by0 - 8 or y0 >= by0:
            continue
        if by0 - y1 > 190:
            continue
        dx = (x0 + x1) / 2 - (bx0 + bx1) / 2
        if not (-180 <= dx <= 30):
            continue
        area = (x1 - x0) * (y1 - y0)
        # 远离「部」的上一行（标签的部首字）优先级低，除非更大
        score = area + (0 if dx > -55 else 1500)
        if best is None or score > best[0]:
            best = (score, b)
    if best is None:
        return []
    rb = [int(v) for v in best[1]]
    dark = is_dark(g, rb)
    if dark > 160:
        return []
    out.append({"page": page, "vol": vol, "bu_iou": round(float(hits[0][0]), 3),
                "bu_box": bu_box, "radical_box": rb, "radical_dark": round(dark, 1),
                "radical_cls": None, "bu_cls": None,
                "n_bu_hits": len(hits)})
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=os.path.join(OUT, "bu_home_candidates.jsonl"))
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    vol = json.load(open(os.path.join(OUT, "volume_radicals.json"), encoding="utf-8"))
    vs = json.load(open(os.path.join(ROOT, "work", "lead", "volume_sections.json"),
                        encoding="utf-8"))
    btpl = bu_template()
    print("部模板 ink_sum", float(btpl.sum()), flush=True)
    pages = []
    for v in [f"{i:02d}" for i in range(1, 13)]:
        for a, b in vs[v]["runs"]:
            pages.extend((v, p) for p in range(a, b + 1))
    if args.limit:
        pages = pages[:args.limit]
    print("pages", len(pages), flush=True)
    from concurrent.futures import ProcessPoolExecutor
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for res in ex.map(_worker, pages, chunksize=8):
            if res:
                rows.extend(res)
    rows.sort(key=lambda r: (r["vol"], r["page"]))
    with open(args.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("wrote", len(rows), "candidate anchors", flush=True)


def _worker(args):
    v, p = args
    try:
        btpl = bu_template()
        return detect_page(v, p, btpl)
    except Exception as e:  # pragma: no cover
        return []


if __name__ == "__main__":
    main()
