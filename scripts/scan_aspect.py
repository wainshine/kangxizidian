#!/usr/bin/env python3
"""字框几何体检：大字形应接近 1:1 且面积约为小字 4 倍。

对每个字计算：
  box_aspect   = min(box_w,box_h)/max(...)         （字框方度）
  ink_aspect   = min(ink_w,ink_h)/max(...)         （成品字形方度，256px 渲染）
  ink_vs_small = glyph_ink_area / 本页小字组件中位面积   （应 ≈ 2~8）
  glyph_fill   = glyph_ink_area / 源框墨量（比例过低=切偏/切走）
输出 work/lead/aspect_scan.jsonl
"""
import json, os, sys
import numpy as np
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))


def worker(args):
    page, half, items, font = args[0], args[1], args[2], args[3]
    import cv2
    import font_build as FB
    import font_norm as FN
    from fidelity_eval import glyph_mask_from_font
    out = []
    try:
        g = FB.page_gray(page[:2], int(page[3:])) if hasattr(FB, "page_gray") else None
        from detect_blocks import page_gray, binarize
        g = page_gray(page[:2], int(page[3:]))
        ink = binarize(g)
        h, w = g.shape
        col = ink.sum(axis=0).astype(np.float32)
        lo, hi = int(w * 0.42), int(w * 0.58)
        gx = int(lo + np.argmin(col[lo:hi]))
        mask = (lambda x, y: x < gx) if half == "L" else (lambda x, y: x >= gx)
        n, lab, st, _ = cv2.connectedComponentsWithStats(ink, 8)
        small_areas = []
        for i in range(1, n):
            x, y, ww, hh, a = [int(v) for v in st[i]]
            if not mask(x + ww / 2, y + hh / 2):
                continue
            if 24 <= hh <= 54 and 9 <= ww <= 60 and 40 <= a <= 1200:
                small_areas.append(a)
        s_ink = float(np.median(small_areas)) if small_areas else 150.0
    except Exception as e:
        return [(it["char"], f"page:{e}") for it in items]
    for it in items:
        ch, box = it["char"], it["box"]
        try:
            bw, bh = box[2] - box[0], box[3] - box[1]
            box_aspect = min(bw, bh) / max(1, max(bw, bh))
            # 源框墨迹
            pad = 8
            x0, y0 = max(0, box[0] - pad), max(0, box[1] - pad)
            x1, y1 = min(w, box[2] + pad), min(h, box[3] + pad)
            crop = ink[y0:y1, x0:x1]
            ix0, iy0 = box[0] - x0, box[1] - y0
            ix1, iy1 = ix0 + bw, iy0 + bh
            inside = crop[iy0:iy1, ix0:ix1]
            src_area = int(inside.sum())
            ys, xs = np.nonzero(inside)
            if len(xs) == 0:
                continue
            ink_w = int(xs.max() - xs.min() + 1); ink_h = int(ys.max() - ys.min() + 1)
            ink_aspect = min(ink_w, ink_h) / max(1, max(ink_w, ink_h))
            # 切偏检测：框外 4px 环内墨量（与框内相连视为继续）
            ring = crop.copy(); ring[iy0:iy1, ix0:ix1] = 0
            ring_area = int(ring[:, :].sum())
            ratio_small = src_area / max(1.0, s_ink)
            # 成品字形方度（字体渲染）
            gm = glyph_mask_from_font(font, ch)
            gys, gxs = np.nonzero(gm)
            g_aspect = (min(gxs.max() - gxs.min() + 1, gys.max() - gys.min() + 1) /
                        max(1, max(gxs.max() - gxs.min() + 1, gys.max() - gys.min() + 1))) if len(gxs) else 1.0
            flags = []
            if ink_aspect < 0.40:
                flags.append("ink_flat")
            if ratio_small < 2.0:
                flags.append("area_small")
            if ratio_small > 11.0:
                flags.append("area_big")
            if ring_area > 0.25 * max(1, src_area):
                flags.append("ring_ink")   # 框外有大量墨 → 切偏/框偏小
            if box_aspect < 0.55:
                flags.append("box_narrow")
            if g_aspect < 0.35:
                flags.append("glyph_flat")
            if flags:
                out.append({"char": ch, "page": page, "half": half, "box": box,
                            "box_aspect": round(box_aspect, 3),
                            "ink_aspect": round(ink_aspect, 3),
                            "glyph_aspect": round(g_aspect, 3),
                            "ratio_small": round(ratio_small, 2),
                            "ring_ratio": round(ring_area / max(1, src_area), 3),
                            "src_area": src_area, "s_ink": round(s_ink, 1),
                            "flags": flags})
        except Exception:
            pass
    return out


def main():
    font, man_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    man = json.load(open(os.path.join(ROOT, man_path), encoding="utf-8"))["chars"]
    by_page = {}
    for ch, r in man.items():
        by_page.setdefault((r["page"], r.get("half", "L")), []).append({"char": ch, "box": r["box"]})
    jobs = [(p, h, items, font) for (p, h), items in by_page.items()]
    rows = []
    with ProcessPoolExecutor(max_workers=8) as ex:
        for res in ex.map(worker, jobs, chunksize=2):
            rows.extend(res)
    rows.sort(key=lambda r: (r.get("ink_aspect", 1) if "ink_aspect" in r else 1))
    with open(out_path, "w", encoding="utf-8") as fo:
        for r in rows:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    c = Counter()
    for r in rows:
        for f in r.get("flags", []):
            c[f] += 1
    print(json.dumps({"flagged": len(rows), "by_flag": dict(c)}))


if __name__ == "__main__":
    main()
