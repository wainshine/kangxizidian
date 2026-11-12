#!/usr/bin/env python3
"""框线逃逸闸（v2.6 起）：验证「切前排除」后，块内是否仍有贯穿块的长直线带残留。

判据：在字符 block 区内，若存在整行/整列墨带（长度 ≥ 0.92×块宽/块高、厚度 ≤10px、
且延伸出块边继续有墨），视为框线逃逸 → 该字不合格。
输出 work/lead/frame_escape_scan_<tag>.jsonl；退出码 0（仅报告；由 release_gate 判定）。
"""

# --- 并发守卫（AGENTS.md：≤10 workers / CPU≤2000%；先限线程再导入重库）---
import os as _os
for _k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ.setdefault(_k, "1")
try:
    import cv2 as _cv2
    _cv2.setNumThreads(1)
except Exception:
    pass



import argparse, json, os, sys
import numpy as np
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))


def _block_rect(page, half, box, fb, tbb):
    lat = fb.get_page_lattice(page).get(half)
    block = fb.block_for_box(lat, box)
    if block is not None and tbb is not None:
        block = (max(block[0], tbb[0]), max(block[1], tbb[1]),
                 min(block[2], tbb[2]), min(block[3], tbb[3]))
    return block


def worker(args):
    page, half, items = args
    import cv2
    import font_build as fb
    import font_norm as FN
    from page_frames import detect_content_quads
    from detect_blocks import page_gray
    out = []
    try:
        quads = detect_content_quads(page_gray(page[:2], int(page[3:])))
        tbb = fb.get_page_text_bbox(page)
        quad = quads.get(half)
    except Exception:
        return []
    for it in items:
        ch, box = it["char"], it["box"]
        try:
            block = _block_rect(page, half, box, fb, tbb)
            gray = FN.render_pdf_crop(page, box, pad150=6, dpi=300)
            ink = FN.binarize(gray)
            if quad is not None:
                from page_frames import clip_mask_page
                cm = clip_mask_page(gray.shape, (box[0] - 6, box[1] - 6), quad)
                ink = ink & cm
            ink = FN.strip_crop_frame_bands(ink)
            filled = ink.astype(np.uint8)
            if block is None:
                continue
            ox = (box[0] - 6) * 2.0; oy = (box[1] - 6) * 2.0
            x0 = int(round(block[0] * 2 - ox)); y0 = int(round(block[1] * 2 - oy))
            x1 = int(round(block[2] * 2 - ox)); y1 = int(round(block[3] * 2 - oy))
            sub = filled[max(0, y0):y1, max(0, x0):x1]
            if sub.size == 0:
                continue
            hh, ww = sub.shape
            bad = 0
            for yy in range(hh):
                if sub[yy].mean() >= 0.92 and sub[yy].sum() >= 0.5 * ww:
                    bad += 1
            for xx in range(ww):
                if sub[:, xx].mean() >= 0.92 and sub[:, xx].sum() >= 0.5 * hh:
                    bad += 1
            if bad >= 2:
                out.append({"char": ch, "page": page, "half": half, "box": box,
                            "line_rows_cols": int(bad)})
        except Exception:
            pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    man = json.load(open(os.path.join(ROOT, args.manifest), encoding="utf-8"))["chars"]
    by = {}
    for ch, r in man.items():
        by.setdefault((r["page"], r.get("half", "")), []).append({"char": ch, "box": r["box"]})
    jobs = [(p, h, items) for (p, h), items in by.items()]
    rows = []
    with ProcessPoolExecutor(max_workers=8) as ex:
        for res in ex.map(worker, jobs, chunksize=2):
            rows.extend(res)
    rows.sort(key=lambda r: r["char"])
    with open(os.path.join(ROOT, args.out), "w", encoding="utf-8") as fo:
        for r in rows:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"flagged": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
