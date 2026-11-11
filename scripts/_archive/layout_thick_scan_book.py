#!/usr/bin/env python3
"""全量版面法大字检测（150dpi，8 进程）→ work/lead/layout_big_boxes.jsonl
每条：page/half/box150/p90/ink_area/h0。同时输出每页小字数用于面积校验。
"""
import json, os, sys
import numpy as np, cv2, fitz
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def detect_page(args):
    vol, pno, dpi = args  # dpi=300：与验过页一致的阈值体系
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
    pix = doc[pno - 1].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    doc.close()
    bg = cv2.medianBlur(gray, 41)  # 必须 > 大字笔画厚度，否则粗笔画被背景吃掉
    norm = np.clip(gray.astype(np.int16) - bg.astype(np.int16) + 200, 0, 255).astype(np.uint8)
    thr, _ = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = (norm < min(205, int(thr))).astype(np.uint8)
    n0, l0, s0, _ = cv2.connectedComponentsWithStats(ink, 8)
    allow = (s0[:, cv2.CC_STAT_AREA] >= 25)
    allow[0] = False
    ink = allow[l0].astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, 8)
    comps = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a < 40:
            continue
        sub = (lab[y:y + h, x:x + w] == i).astype(np.uint8)
        dt = cv2.distanceTransform(sub, cv2.DIST_L2, 3)
        v = dt[dt > 0]
        p90 = float(np.percentile(v, 90)) if v.size else 0.0
        comps.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h), "a": int(a), "p90": p90})
    small = [c for c in comps if 56 <= c["h"] <= 96 and c["a"] < 3200]
    if not small:
        return {"page": f"{vol}_{pno:04d}", "boxes": [], "meta": {"empty": True}}
    h0 = float(np.median([c["h"] for c in small]))
    small_p90 = float(np.median([c["p90"] for c in small]))
    small_area = float(np.median([c["a"] for c in small]))
    seeds = [c for c in comps if c["p90"] >= max(4.2, 1.7 * small_p90) and c["w"] >= 10 and c["h"] >= 8]
    def near(a, b, gap=26):
        return not (a["x"] + a["w"] + gap < b["x"] or b["x"] + b["w"] + gap < a["x"] or
                    a["y"] + a["h"] + gap < b["y"] or b["y"] + b["h"] + gap < a["y"])
    groups = [dict(c) for c in seeds]
    changed = True
    while changed:
        changed = False
        out = []
        used = [False] * len(groups)
        for i in range(len(groups)):
            if used[i]:
                continue
            gi = dict(groups[i])
            for j in range(i + 1, len(groups)):
                if used[j]:
                    continue
                gj = groups[j]
                if near(gi, gj):
                    x0 = min(gi["x"], gj["x"]); y0 = min(gi["y"], gj["y"])
                    x1 = max(gi["x"] + gi["w"], gj["x"] + gj["w"])
                    y1 = max(gi["y"] + gi["h"], gj["y"] + gj["h"])
                    if (x1 - x0) > 2.7 * h0 or (y1 - y0) > 2.7 * h0:
                        continue
                    gi = {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0,
                          "a": gi.get("a", 0) + gj.get("a", 0),
                          "p90": max(gi.get("p90", 0), gj.get("p90", 0))}
                    used[j] = True; changed = True
            out.append(gi)
        groups = out
    # 扁平横画合并
    gs = sorted(groups, key=lambda g: -g["w"])
    used = [False] * len(gs); merged = []
    for i, a in enumerate(gs):
        if used[i]:
            continue
        gi = dict(a)
        for j in range(i + 1, len(gs)):
            if used[j]:
                continue
            b = gs[j]
            if not (gi["h"] < 0.55 * gi["w"] and b["h"] < 0.55 * b["w"]):
                continue
            ox = max(0, min(gi["x"] + gi["w"], b["x"] + b["w"]) - max(gi["x"], b["x"]))
            if ox < 0.6 * min(gi["w"], b["w"]):
                continue
            gap = max(gi["y"], b["y"]) - min(gi["y"] + gi["h"], b["y"] + b["h"])
            if gap <= 95:
                x0 = min(gi["x"], b["x"]); y0 = min(gi["y"], b["y"])
                x1 = max(gi["x"] + gi["w"], b["x"] + b["w"]); y1 = max(gi["y"] + gi["h"], b["y"] + b["h"])
                if (y1 - y0) <= 2.7 * h0 and (x1 - x0) <= 2.7 * h0:
                    gi = {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0,
                          "a": gi.get("a", 0) + b.get("a", 0),
                          "p90": max(gi.get("p90", 0), b.get("p90", 0))}
                    used[j] = True
        merged.append(gi)
    boxes = []
    for g in merged:
        if not (1.35 * h0 <= max(g["w"], g["h"]) <= 2.75 * h0):
            continue
        if min(g["w"], g["h"]) < 0.55 * h0:
            continue
        if not (1.0 * small_area <= g["a"] <= 6.5 * small_area):
            continue
        boxes.append({"box": [int(round(g["x"] / 2)), int(round(g["y"] / 2)),
                              int(round((g["x"] + g["w"]) / 2)), int(round((g["y"] + g["h"]) / 2))],
                      "p90": round(g["p90"], 2), "ink": int(g["a"])})
    return {"page": f"{vol}_{pno:04d}", "h0_150": round(h0 / 2, 1),
            "small_p90_150": round(small_p90 / 2, 2), "small_area_150": round(small_area / 4, 1),
            "n_small": len(small), "boxes": boxes}


def main():
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    jobs = []
    for vol, fn in sorted(mp.items()):
        doc = fitz.open(os.path.join(ROOT, "康熙字典", fn))
        n = doc.page_count
        doc.close()
        for p in range(1, n + 1):
            jobs.append((vol, p, 300))
    print("pages", len(jobs), flush=True)
    out = os.path.join(ROOT, "work/lead/layout_big_boxes.jsonl")
    n_ok = 0
    with ProcessPoolExecutor(max_workers=8) as ex, open(out, "w", encoding="utf-8") as fo:
        for i, res in enumerate(ex.map(detect_page, jobs, chunksize=8)):
            fo.write(json.dumps(res, ensure_ascii=False) + "\n")
            n_ok += 1
            if n_ok % 400 == 0:
                print("done", n_ok, flush=True)
    print("finished", n_ok, out, flush=True)


if __name__ == "__main__":
    main()
