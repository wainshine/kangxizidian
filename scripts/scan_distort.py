#!/usr/bin/env python3
"""字形变形体检（参考对比口径）：长宽比 / 大小 与参考字体同字差异超过阈值 → 疑似切偏/变形。

指标：
  aspect_ratio = (glyph_ink_w/h) / (ref_ink_w/h)   （字形长宽比相对参考的倍数）
  size_ratio   = (glyph_ink_area / block_w/h) / (ref_ink_area / ref_bbox_area)
输出 work/lead/distort_scan.jsonl
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
    from refgate import raster as ref_raster, SONGTI
    out = []
    try:
        lat = FB.get_page_lattice(page).get(half)
        tbb = FB.get_page_text_bbox(page)
    except Exception:
        return [(it["char"], "prepare") for it in items]
    for it in items:
        ch, box = it["char"], it["box"]
        try:
            block = FB.block_for_box(lat, box)
            if block is not None and tbb is not None:
                block = (max(block[0], tbb[0]), max(block[1], tbb[1]),
                         min(block[2], tbb[2]), min(block[3], tbb[3]))
            gm = glyph_mask_from_font(font, ch)
            ys, xs = np.nonzero(gm)
            if len(xs) == 0:
                continue
            gw, gh = int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
            ga = int(gm.sum())
            ref = ref_raster(SONGTI, ch, 256, index=7)
            rys, rxs = np.nonzero(ref)
            if len(rxs) == 0:
                continue
            rw, rh = int(rxs.max() - rxs.min() + 1), int(rys.max() - rys.min() + 1)
            ra = int(ref.sum())
            aspect_g = gw / max(1, gh); aspect_r = rw / max(1, rh)
            aspect_ratio = max(aspect_g / max(1e-6, aspect_r), aspect_r / max(1e-6, aspect_g))
            # 归一化大小：字形 ink 面积 / (字形 bbox 面积) vs 参考
            size_g = ga / max(1.0, gw * gh); size_r = ra / max(1.0, rw * rh)
            size_ratio = size_g / max(1e-6, size_r)
            flags = []
            if aspect_ratio > 1.75:
                flags.append("aspect")
            if size_ratio < 0.62 or size_ratio > 1.6:
                flags.append("size")
            if gw * gh < 0.35 * max(1, (block[2] - block[0]) * (block[3] - block[1])) if block else False:
                flags.append("tiny_vs_block")
            if flags:
                out.append({"char": ch, "page": page, "half": half, "box": box,
                            "aspect_ratio": round(aspect_ratio, 3),
                            "size_ratio": round(size_ratio, 3),
                            "glyph_w": gw, "glyph_h": gh,
                            "ref_w": rw, "ref_h": rh, "flags": flags})
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
    rows.sort(key=lambda r: -(r.get("aspect_ratio") or 0))
    with open(out_path, "w", encoding="utf-8") as fo:
        for r in rows:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    c = Counter()
    for r in rows:
        for f in r.get("flags", []):
            c[f] += 1
    print(json.dumps({"flagged": len(rows), "by_flag": dict(c),
                      "aspect_top": [f"{r['char']}:{r['aspect_ratio']}" for r in rows[:15]]}))


if __name__ == "__main__":
    main()
