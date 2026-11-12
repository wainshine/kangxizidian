#!/usr/bin/env python3
"""生成 block-based mapping（类级修复）：box = 2×2 格块（页级 lattice），
再与版框内正文区（content quad）求交；**不再使用字内墨迹紧框**。

并行：按页分组，进程池（默认 8 workers；FONT_BUILD_WORKERS 可调）。
输出 mapping_block_v<ver>.jsonl（格式同 mapping33）。
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
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))


def _shrink_box_past_bands(page, box, pad=12):
    """裁片级：若 box 边附近存在贯穿裁片的框线带，把该边推过去（只动外带，不碰字身）。"""
    import numpy as np
    import font_norm as FN
    try:
        gray = FN.render_pdf_crop(page, box, pad150=pad, dpi=300)
        ink = FN.binarize(gray)
    except Exception:
        return box
    h, w = ink.shape
    x0, y0, x1, y1 = [float(v) for v in box]
    # box 在 crop 坐标：pad*2 边距
    px = pad * 2
    for _ in range(2):
        rows = np.where(ink.mean(axis=1) >= 0.45)[0]
        cols = np.where(ink.mean(axis=0) >= 0.45)[0]
        def runs(idx):
            return np.split(idx, np.where(np.diff(idx) > 1)[0] + 1) if len(idx) else []
        # 上边：仅在 box 上边线以上/附近的带（crop 顶部 2*pad+10 内）
        for r in runs(rows):
            if r[-1] - r[0] + 1 > 16: continue
            yc = (r[0] + r[-1]) / 2.0
            if yc < px:
                y0 = max(y0, y0 + (r[-1] + 1) / 2.0 - (px - 0) / 2.0)  # 近似：推到带下
        for c in runs(cols):
            if c[-1] - c[0] + 1 > 16: continue
            xc = (c[0] + c[-1]) / 2.0
            if xc < px:
                x0 = max(x0, x0 + (c[-1] + 1) / 2.0)
    return [round(v) for v in (x0, y0, x1, y1)]


def worker(args):
    page, half, items = args
    import font_build as fb
    try:
        # 统一入口（含页级几何缓存 + lattice fallback；审计 P0-3）
        quads = fb.get_page_content_quads(page)
        lat = fb.get_page_lattice(page).get(half)
        q = quads.get(half)
    except Exception:
        return []
    out = []
    for it in items:
        ch, old = it["char"], it["box"]
        block = fb.block_for_box(lat, old) if lat else None
        if block is None:
            continue
        nb = list(block)
        if q is not None:
            qb = q["box"]
            nb = [max(nb[0], qb[0] + 2), max(nb[1], qb[1] + 2),
                  min(nb[2], qb[2] - 2), min(nb[3], qb[3] - 2)]
        nb = [float(round(v)) for v in nb]
        if nb[2] - nb[0] < 60 or nb[3] - nb[1] < 60:
            continue
        out.append((it.get("rid"), ch, nb))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    rows = [json.loads(l) for l in open(os.path.join(ROOT, args.mapping), encoding="utf-8")]
    jobs = {}
    for r in rows:
        items, seen = [], set()
        for idx_a, a in enumerate(r.get("assigned", [])):
            ch = a.get("char"); cand = a.get("cand") or {}
            box = cand.get("box") or a.get("box")
            if ch and box and ch not in seen:
                seen.add(ch)
                items.append({"char": ch, "box": box,
                              "rid": f"{r.get('page')}|{idx_a}|{ch}"})
        # 注意：重复字跨页时按行处理（rid 唯一），不再用 newmap[ch] 全局覆盖
        if items:
            jobs.setdefault((r["page"], r.get("half", "")), []).extend(items)
    jl = [(p, h, items) for (p, h), items in jobs.items()]
    newmap = {}
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for res in ex.map(worker, jl, chunksize=2):
            for rid, ch, nb in res:
                newmap[(rid, ch)] = nb
    changed = 0
    for r in rows:
        for idx_a, a in enumerate(r.get("assigned", [])):
            ch = a.get("char")
            rid = f"{r.get('page')}|{idx_a}|{ch}"
            if rid in newmap:
                cand = dict(a.get("cand") or {})
                old = cand.get("box") or a.get("box")
                if [float(round(v)) for v in old] != newmap[rid, ch]:
                    changed += 1
                cand["box"] = newmap[rid, ch]
                a["cand"] = cand
    with open(os.path.join(ROOT, args.out), "w", encoding="utf-8") as fo:
        for r in rows:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"pages": len(jl), "boxed": len(newmap), "changed": changed}))


if __name__ == "__main__":
    main()
